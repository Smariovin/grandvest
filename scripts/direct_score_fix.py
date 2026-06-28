#!/usr/bin/env python3
import sqlite3, json, re, subprocess, time, urllib.request, urllib.parse, os

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)
    except: pass

NEW_FILTER = """const content = $input.first().json.choices?.[0]?.message?.content || '';
let score = 0;
let reason = '';
try {
  let cleaned = content.trim().replace(/```(?:json)?\\s*/gi,'').replace(/```/g,'').trim();
  if (cleaned.startsWith('{')) {
    const parsed = JSON.parse(cleaned);
    score = parseInt(parsed.score) || 0;
    reason = parsed.reason || '';
  } else {
    const m = content.match(/\\b([1-9]|10)\\b/);
    score = m ? parseInt(m[1]) : 0;
  }
} catch(e) { score = 0; }
console.log('Score:', score, '| Reason:', reason);
if (score >= 5) {
  const src = $('2. Дедупликация входящих').first().json;
  return [{ json: { ...src, score, score_reason: reason } }];
}
console.log('FILTERED: score=' + score + ' < 5');
return [];"""

subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()
fixes = []

for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue
    changed = False
    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
        if 'фильтр' in name.lower() and 'code' in ntype.lower():
            old_thresh = re.findall(r'score\s*>=?\s*(\d+)', code)
            n['parameters']['jsCode'] = NEW_FILTER
            n['parameters'].pop('code', None)
            changed = True
            fixes.append(f"[{wf_name}] '{name}': порог {old_thresh}→5")
            print(f"Fixed: {wf_name} / {name} | old={old_thresh}")
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(12):
    time.sleep(5)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

# Также проверяем статус бота
BOT_TOKEN = os.environ.get('BOT_TOKEN','')
if BOT_TOKEN:
    try:
        req = urllib.request.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/getMe')
        with urllib.request.urlopen(req, timeout=10) as r:
            bot = json.loads(r.read().decode()).get('result',{})
            bot_id = bot.get('id')
            print(f'Bot: @{bot.get("username")} id={bot_id}')
        
        req2 = urllib.request.Request(
            f'https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id=-1003971323034&user_id={bot_id}')
        with urllib.request.urlopen(req2, timeout=10) as r2:
            member = json.loads(r2.read().decode()).get('result',{})
            status = member.get('status','?')
            print(f'Bot channel status: {status}')
            
            is_admin = status in ('administrator','creator')
            tg(
                f'<b>🤖 @Grandvest_bot в канале</b>\n\n'
                f'Статус: <b>{status}</b>\n'
                f'Администратор: {"✅ Да" if is_admin else "❌ Нет"}\n'
                + ('' if is_admin else
                   '\n⚠️ Для полной верификации публикаций добавь бота администратором:\n'
                   '1. Канал → Настройки → Администраторы\n'
                   '2. Найди @Grandvest_bot\n'
                   '3. Включи право "Читать сообщения"')
            )
    except Exception as e:
        print(f'Bot check error: {e}')
        tg(f'⚠️ Не удалось проверить статус бота: {e}')

tg(
    f'✅ <b>Порог оценки снижен до 5</b>\n\n'
    + '\n'.join(f'• {f}' for f in fixes) +
    '\n\n<b>Шкала оценки Claude (1-10):</b>\n'
    '🟢 8-10: прямо о недвижимости, с цифрами\n'
    '🟡 6-7: ипотека, инвестиции, строительство\n'
    '🟡 5: около-рыночная тема → <b>теперь проходит</b>\n'
    '🔴 1-4: нерелевантно → отфильтровывается\n\n'
    'Ожидаемый результат: 5-15 публикаций в рабочий день'
)
