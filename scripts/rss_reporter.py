#!/usr/bin/env python3
"""
RSS Reporter — добавляет детальный отчёт в RSS workflow n8n
Вставляется как Code узел после Merge, перед HTTP Request6
"""

# Этот код вставляется в n8n как Code узел "Отчёт RSS парсинга"
RSS_REPORT_CODE = """
// Отчёт RSS парсинга
const items = $input.all();
const now = new Date();
const mskOffset = 3 * 60 * 60 * 1000;
const msk = new Date(now.getTime() + mskOffset);
const timeStr = msk.toISOString().slice(11,16);
const dateStr = msk.toISOString().slice(0,10).split('-').reverse().join('.');

// Группируем по источнику
const bySource = {};
for (const item of items) {
  const src = item.json.source || item.json.feedName || item.json.link?.split('/')[2] || 'Unknown';
  if (!bySource[src]) bySource[src] = [];
  bySource[src].push(item.json.title || item.json.description || '?');
}

const sources = Object.keys(bySource);
const total = items.length;

// Строим отчёт
let report = `📊 <b>Отчёт парсинга RSS | ${timeStr} МСК</b>\\n`;
report += `📅 ${dateStr} | Парсер RSS\\n\\n`;
report += `<b>Итого:</b>\\n`;
report += `📡 Источников с новостями: ${sources.length}\\n`;
report += `📰 Всего новых новостей: ${total}\\n`;
report += `✅ Отобрано для генерации: 1 (лучшая)\\n\\n`;
report += `<b>По источникам:</b>\\n`;

for (const [src, titles] of Object.entries(bySource)) {
  report += `✅ ${src} — ${titles.length} новостей\\n`;
  if (titles[0]) {
    report += `   💬 ${titles[0].substring(0, 60)}...\\n`;
  }
}

// Отправляем отчёт в Telegram
const botToken = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw';
const chatId = '5340000158';

await this.helpers.httpRequest({
  method: 'POST',
  url: `https://api.telegram.org/bot${botToken}/sendMessage`,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    chat_id: chatId,
    text: report,
    parse_mode: 'HTML',
    disable_web_page_preview: true
  })
});

// Берём первый item для дальнейшей обработки
return [items[0]];
"""

print("RSS Report Code готов!")
print(RSS_REPORT_CODE[:200])

import sqlite3, json, subprocess, time, urllib.request, urllib.parse

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)
    except: pass

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
    
    is_rss = 'RSS' in wf_name or 'сбор' in wf_name.lower()
    if not is_rss: continue
    
    print(f"RSS WF: {wf_name}")
    
    # Проверяем есть ли уже узел отчёта
    has_report = any('Отчёт' in n.get('name','') or 'Reporter' in n.get('name','') 
                     for n in nodes)
    if has_report:
        print("  Report node already exists, updating...")
    
    # Находим узел Merge чтобы вставить после него
    merge_node = None
    merge_pos = None
    for n in nodes:
        if n.get('type','') == 'n8n-nodes-base.merge' or 'Merge' in n.get('name',''):
            merge_node = n
            merge_pos = n.get('position', [0, 0])
            print(f"  Found Merge at {merge_pos}")
            break
    
    # Добавляем/обновляем Code узел отчёта
    report_node = None
    for n in nodes:
        if 'Отчёт RSS' in n.get('name','') or 'RSS Report' in n.get('name',''):
            report_node = n
            break
    
    if report_node is None and merge_pos:
        # Создаём новый узел
        new_node = {
            "id": "rss-reporter-001",
            "name": "Отчёт RSS парсинга",
            "type": "n8n-nodes-base.code",
            "position": [merge_pos[0] + 200, merge_pos[1]],
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": RSS_REPORT_CODE.strip()
            },
            "typeVersion": 2
        }
        nodes.append(new_node)
        fixes.append(f"[{wf_name}] Добавлен узел 'Отчёт RSS парсинга'")
        print("  Added RSS report node!")
    elif report_node:
        report_node['parameters']['jsCode'] = RSS_REPORT_CODE.strip()
        fixes.append(f"[{wf_name}] Обновлён узел 'Отчёт RSS парсинга'")
        print("  Updated RSS report node!")
    
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

print(f"Fixes: {fixes}")
if fixes:
    tg('✅ <b>RSS отчёт добавлен в workflow</b>\n' + '\n'.join(f'• {f}' for f in fixes))
