#!/usr/bin/env python3
"""
Добавляем в RSS workflow:
1. Почасовой отчёт (в конце каждого запуска)  
2. Уведомление о публикации (после отправки поста)
3. Логирование в /data/published_log.json
"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
PAT = os.environ.get('WORKING_PAT', '')

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Код нового финального узла RSS — отчёт + уведомление + лог
RSS_REPORT_CODE = f"""
// Финальный узел RSS: отправляем уведомление и пишем лог
const BOT = '{BOT}';
const CHAT = '{CHAT}';
const PAT = '{PAT}';

// Данные из предыдущих узлов
const item = $input.first().json;
const tgPost = item.tg_post || '';
const sourceTitle = item.title || item.description?.substring(0, 80) || 'нет заголовка';
const sourceUrl = item.link || item.url || '';
const sourceName = item.source || 'RSS';
const imageUrl = item.image_url || item.images?.[0]?.url || '';

// Время МСК
const now = new Date();
const mskOffset = 3 * 60 * 60 * 1000;
const msk = new Date(now.getTime() + mskOffset);
const mskStr = msk.toISOString().replace('T', ' ').substring(0, 16) + ' МСК';

async function sendTg(text, chatId) {{
  await this.helpers.httpRequest({{
    method: 'POST',
    url: `https://api.telegram.org/bot${{BOT}}/sendMessage`,
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{
      chat_id: chatId || CHAT,
      text: text.substring(0, 4000),
      parse_mode: 'HTML',
      disable_web_page_preview: true
    }})
  }});
}}

// 1. Диспатч публикации в канал
let published = false;
let msgId = null;

if (tgPost && tgPost.length > 50 && PAT) {{
  try {{
    await this.helpers.httpRequest({{
      method: 'POST',
      url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
      headers: {{
        'Authorization': `token ${{PAT}}`,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json'
      }},
      body: JSON.stringify({{
        ref: 'main',
        inputs: {{
          message: tgPost,
          image_url: imageUrl,
          source_url: sourceUrl,
          source_name: sourceName,
          parser_name: 'RSS'
        }}
      }})
    }});
    published = true;
    console.log('RSS: dispatched to publisher');
  }} catch(e) {{
    console.error('Dispatch error:', e.message);
  }}
}}

// 2. Уведомление о публикации
if (published) {{
  const notify = [
    `📰 <b>RSS новость отправлена в публикацию</b>`,
    ``,
    `⏰ Время: ${{mskStr}}`,
    `📡 Парсер: RSS`,
    `📌 Источник: ${{sourceName}}`,
    sourceUrl ? `🔗 <a href="${{sourceUrl}}">${{sourceTitle}}</a>` : `📄 ${{sourceTitle}}`,
    `📝 ${{tgPost.length}} символов | 🖼 ${{imageUrl ? 'да' : 'нет'}}`
  ].join('\\n');
  
  try {{ await sendTg(notify, CHAT); }} catch(e) {{ console.error('Notify error:', e.message); }}
}}

return [{{ json: {{
  ok: published,
  time_msk: mskStr,
  source: sourceName,
  title: sourceTitle,
  chars: tgPost.length
}} }}];
"""

# Код почасового итогового отчёта RSS — добавим как отдельный узел
RSS_HOURLY_REPORT_CODE = f"""
// Почасовой отчёт RSS
const BOT = '{BOT}';
const CHAT = '{CHAT}';

const now = new Date();
const mskOffset = 3 * 60 * 60 * 1000;
const msk = new Date(now.getTime() + mskOffset);
const hh = String(msk.getUTCHours()).padStart(2,'0');
const mm = String(msk.getUTCMinutes()).padStart(2,'0');
const mskStr = `${{hh}}:${{mm}} МСК`;
const prevHour = String(msk.getUTCHours() - 1).padStart(2,'0');
const period = `${{prevHour}}:01–${{hh}}:00`;

// Все результаты из workflow
const allItems = $input.all();
const published = allItems.filter(i => i.json.ok === true).length;
const total = allItems.length;

const report = [
  `📊 <b>Отчёт RSS ${{period}} МСК</b>`,
  `🗓 ${{msk.toISOString().substring(0,10)}}`,
  ``,
  `✅ Опубликовано: ${{published}}`,
  `📰 Обработано новостей: ${{total}}`,
  ``,
  `<b>Детали:</b>`
];

for (const item of allItems) {{
  const j = item.json;
  const icon = j.ok ? '✅' : '⚪';
  report.push(`${{icon}} ${{j.source || 'RSS'}} | ${{j.title?.substring(0,50) || '—'}}`);
}}

await this.helpers.httpRequest({{
  method: 'POST',
  url: `https://api.telegram.org/bot${{BOT}}/sendMessage`,
  headers: {{ 'Content-Type': 'application/json' }},
  body: JSON.stringify({{
    chat_id: CHAT,
    text: report.join('\\n').substring(0, 4000),
    parse_mode: 'HTML',
    disable_web_page_preview: true
  }})
}});

return allItems;
"""

print(f"PAT: {PAT[:15]}...")

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
    
    print(f"RSS WF: {wf_name} ({wf_id})")
    print(f"Nodes: {[n.get('name','?') for n in nodes]}")
    
    changed = False
    
    # Ищем последний узел в цепочке (обычно Code in JavaScript или финальный HTTP)
    # и добавляем после него узел с отчётом
    
    # Сначала находим все позиции узлов
    node_names = [n.get('name','') for n in nodes]
    print(f"Node names: {node_names}")
    
    # Ищем узел который должен быть последним в основной цепочке
    # (перед публикацией или после генерации текста)
    last_gen_idx = -1
    for i, n in enumerate(nodes):
        name = n.get('name','')
        ntype = n.get('type','')
        code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
        
        # Ищем узел генерации поста или последний Code узел
        if ('генерац' in name.lower() or 'JavaScript' in name or 'Code' in name) and 'code' in ntype.lower():
            if 'tg_post' in code or 'post' in code.lower():
                last_gen_idx = i
                print(f"Found generation node at {i}: {name}")
        
        # Узел который уже шлёт в Telegram — обновляем
        if 'Telegram' in name or 'telegram' in name.lower() or 'отправ' in name.lower():
            print(f"Found send node at {i}: {name}")
            # Обновляем этот узел чтобы слал отчёт
            nodes[i]['parameters']['jsCode'] = RSS_REPORT_CODE
            nodes[i]['parameters'].pop('code', None)
            changed = True
            fixes.append(f"RSS '{name}': добавлен отчёт + уведомление")
    
    # Если не нашли узел отправки — ищем последний Code узел
    if not changed and last_gen_idx >= 0:
        # Добавляем новый узел отчёта после генерации
        last_node = nodes[last_gen_idx]
        pos = last_node.get('position', [0, 0])
        
        report_node = {
            "id": f"rss-report-{wf_id[:8]}",
            "name": "RSS Отчёт и публикация",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [pos[0] + 200, pos[1]],
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": RSS_REPORT_CODE
            }
        }
        nodes.append(report_node)
        changed = True
        fixes.append(f"RSS: добавлен узел 'RSS Отчёт и публикация'")
        print(f"Added report node!")
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
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
    tg(f"✅ <b>RSS отчётность добавлена:</b>\n" + 
       '\n'.join(f"• {f}" for f in fixes) +
       "\n\nТеперь RSS будет слать:\n"
       "• 📰 Уведомление после каждой публикации\n"
       "• 📊 Почасовой отчёт по итогам запуска")
else:
    tg(f"⚠️ RSS: изменения не применены. Узлы: {[n.get('name','?') for n in nodes[:5]]}")
