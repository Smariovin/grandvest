#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/st_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

curl -s -b /tmp/st_ck.txt \
  'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | python3 << 'PYEOF'
import sys, json, subprocess, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)
    except: pass

d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])

# Новый код фильтра с порогом 5 и подробным логированием
NEW_FILTER = """const content = $input.first().json.choices?.[0]?.message?.content || '';
let score = 0;
let reason = '';

try {
  let cleaned = content.trim()
    .replace(/```(?:json)?\\s*/gi, '')
    .replace(/```/g, '')
    .trim();
  
  if (cleaned.startsWith('{')) {
    const parsed = JSON.parse(cleaned);
    score = parseInt(parsed.score) || 0;
    reason = parsed.reason || '';
  } else {
    const m = content.match(/\\b([1-9]|10)\\b/);
    score = m ? parseInt(m[1]) : 0;
  }
} catch(e) {
  score = 0;
}

console.log(`Score: ${score} | Reason: ${reason} | Content: ${content.substring(0, 80)}`);

// Порог: 5 (снижен с 6 для большего количества публикаций)
// Цель: 5-15 публикаций в рабочий день
if (score >= 5) {
  const src = $('2. Дедупликация входящих').first().json;
  return [{ json: { ...src, score, score_reason: reason } }];
}

// Новость не прошла отбор
console.log(`FILTERED OUT: score=${score} < 5`);
return [];"""

changed = False
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
    
    if 'фильтр' in name.lower() and 'code' in ntype.lower():
        print(f"Found filter node: {name!r}")
        # Проверяем текущий порог
        import re
        thresholds = re.findall(r'score\s*>=?\s*(\d+)', code)
        print(f"Current thresholds: {thresholds}")
        
        n['parameters']['jsCode'] = NEW_FILTER
        n['parameters'].pop('code', None)
        changed = True
        print(f"FIXED: threshold set to >= 5")

if changed:
    r = subprocess.run(['curl','-s','-b','/tmp/st_ck.txt','-X','PUT',
        'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    result = json.loads(r.stdout)
    saved = len(result.get('data',result).get('nodes',[]))
    print(f"Saved: {saved} nodes")
    tg(
        '✅ <b>Порог оценки снижен до 5</b>\n\n'
        'Алгоритм отбора постов:\n'
        '• Claude оценивает новость по шкале 1-10\n'
        '• Порог: ≥ 5 (был ≥ 6)\n'
        '• Цель: 5-15 публикаций в рабочий день\n\n'
        'Критерии оценки Claude:\n'
        '• 8-10: прямо о недвижимости с цифрами\n'
        '• 6-7: косвенно о недвижимости (ипотека, инвестиции)\n'
        '• 5: около-рыночная тема (экономика, строительство)\n'
        '• 1-4: не релевантно → отфильтровывается'
    )
else:
    tg('⚠️ Фильтр не найден')
    print('Filter node not found')
PYEOF
