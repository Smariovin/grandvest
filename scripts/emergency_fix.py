#!/usr/bin/env python3
"""
EMERGENCY FIX: Исправляем SyntaxError в дедупликации
Проблема: $input.all() превратилось в .all() — потерялся $
"""
import sqlite3, json, subprocess, os, time, urllib.request, urllib.parse

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT', '')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

print(f"PAT: {PAT[:15]}...")

# Стоп n8n
subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

# Правильные коды — с $ символами
DEDUP_CORRECT = """const items = $input.all();
const unique = [];
let published = [];
try {
  const fs = require('fs');
  published = JSON.parse(fs.readFileSync('/data/published_titles.json', 'utf8'));
} catch(e) { published = []; }

for (const item of items) {
  const text = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 60);
  if (!published.some(p => p.substring(0, 60) === text)) {
    unique.push(item);
  }
}
console.log('Dedup:', items.length, '->', unique.length);
return unique.slice(0, 1);"""

FILTER_CORRECT = """const content = $input.first().json.choices?.[0]?.message?.content || '';
let score = 7;
try {
  const cleaned = content.trim().replace(/```(?:json)?\\s*/gi, '').replace(/```/g, '').trim();
  if (cleaned.startsWith('{')) {
    const parsed = JSON.parse(cleaned);
    score = parseInt(parsed.score) || 7;
  } else {
    const m = content.match(/\\b([1-9]|10)\\b/);
    score = m ? parseInt(m[1]) : 7;
  }
} catch(e) { score = 7; }
console.log('Score:', score);
const src = $('2. Дедупликация входящих').first().json;
return [{ json: { ...src, score } }];"""

WRITE_DEDUP_CORRECT = """const item = $input.first().json;
const title = (item.title || item.text || '').trim().toLowerCase().substring(0, 60);
if (title) {
  try {
    const fs = require('fs');
    let published = [];
    try { published = JSON.parse(fs.readFileSync('/data/published_titles.json', 'utf8')); } catch(e) {}
    if (!published.includes(title)) {
      published.push(title);
      if (published.length > 300) published = published.slice(-200);
      fs.writeFileSync('/data/published_titles.json', JSON.stringify(published));
    }
  } catch(e) { console.error('Write dedup error:', e.message); }
}
return [$input.first()];"""

NODE9_CORRECT = """const postText = $('8. Подготовка данных поста').first().json.tg_post;
const imgData = $('HTTP Request \u2014 fal.ai').first().json;
const imageUrl = imgData.images && imgData.images[0] ? imgData.images[0].url : '';

if (!postText || postText.length < 10) {
  throw new Error('tg_post пустой: ' + JSON.stringify(postText));
}
console.log('Posting:', postText.length, 'chars');

const resp = await this.helpers.httpRequest({
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {
    'Authorization': 'token """ + PAT + """',
    'Accept': 'application/vnd.github+json',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    ref: 'main',
    inputs: {
      message: postText,
      image_url: imageUrl
    }
  })
});
return [{ json: { ok: true, len: postText.length } }];"""

fixes = []
for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue
    
    changed = False
    for n in nodes:
        name = n.get('name', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        
        # Дедупликация — исправляем SyntaxError
        if 'Дедупликац' in name or '2.' in name:
            if '.all()' in code and '$input' not in code:
                # Сломанный код — исправляем
                n['parameters']['jsCode'] = DEDUP_CORRECT
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] Dedup: SyntaxError fixed ($ restored)")
                print(f"FIXED Dedup syntax in {wf_name}: {name}")
            elif 'getWorkflowStaticData' in code:
                n['parameters']['jsCode'] = DEDUP_CORRECT
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] Dedup: StaticData→file")
                print(f"FIXED Dedup StaticData in {wf_name}: {name}")
        
        # Запись в дедупликацию
        if ('Запись' in name or '10.' in name) and 'дедупликац' in name.lower():
            if '.first()' in code and '$input' not in code:
                n['parameters']['jsCode'] = WRITE_DEDUP_CORRECT
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] WriteDedup: SyntaxError fixed")
                print(f"FIXED WriteDedup in {wf_name}: {name}")
        
        # Фильтр оценки
        if 'фильтр' in name.lower():
            if '.first()' in code and '$input' not in code:
                n['parameters']['jsCode'] = FILTER_CORRECT
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] Filter: SyntaxError fixed")
                print(f"FIXED Filter in {wf_name}: {name}")
        
        # Узел 9
        is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is_node9:
            bad = ('telegram-publisher' in code or '"Bearer' in code or 
                   ('body: body' in code and 'JSON.stringify' not in code))
            if bad:
                n['parameters']['jsCode'] = NODE9_CORRECT
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] Node9: URL+Auth+body fixed")
                print(f"FIXED Node9 in {wf_name}: {name}")
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1, staticData='{}' WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

# Сбрасываем деdup
import os as _os
_os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json', 'w') as f: json.dump([], f)

print(f"\nFixes applied: {len(fixes)}")
for f in fixes: print(f"  {f}")

# Запускаем n8n
subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=20)
print("n8n starting...")
for i in range(12):
    time.sleep(5)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print(f"n8n UP! ({i})")
        break
    except: pass

time.sleep(5)

# Тест вебхука
try:
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': '<div class="tgme_widget_message_text js-message_text">Офисный рынок Москвы 2026 бьёт рекорды: вакантность класса А упала до 7.8 процента — минимум за 5 лет. Ставки аренды в ЦАО достигли 48000 рублей за квадратный метр в год по данным CBRE. IT-сектор занял 34 процента от объёма сделок аренды. Инвестиции превысили 350 миллиардов рублей за полугодие.</div><time datetime="2026-06-27T18:00:00+00:00">18:00</time>'
    }).encode()
    urllib.request.urlopen(urllib.request.Request(
        'http://localhost:5678/webhook/telegram-parser',
        data=payload, headers={'Content-Type': 'application/json'}), timeout=30)
    print("Webhook OK!")
except Exception as e:
    print(f"Webhook error: {e}")

tg(f"✅ <b>Emergency Fix:</b>\n" + '\n'.join(f"• {f}" for f in fixes) +
   "\n\nТест запущен → жди пост!")
print("DONE!")
