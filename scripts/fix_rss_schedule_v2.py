#!/usr/bin/env python3
"""
RSS Time Guard - добавляется в начало RSS workflow как Code узел
Если время вне 08:00-21:00 МСК - останавливает выполнение
"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Код проверки времени для RSS - вставить в Schedule Trigger через cron
# 05:00-18:00 UTC = 08:00-21:00 МСК, каждый час
# cron: "0 5-18 * * *"

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
    
    print(f"RSS: {wf_name}")
    changed = False
    
    for n in nodes:
        ntype = n.get('type','')
        params = n.get('parameters',{})
        
        if 'scheduleTrigger' in ntype:
            print(f"  Current schedule: {json.dumps(params)[:200]}")
            # Каждый час только в 05-18 UTC (08-21 МСК)
            new_params = {
                "rule": {
                    "interval": [
                        {
                            "field": "cronExpression",
                            "expression": "0 5-18 * * *"
                        }
                    ]
                }
            }
            n['parameters'] = new_params
            changed = True
            fixes.append(f"RSS Schedule: каждый час 08:00-21:00 МСК (05-18 UTC)")
            print(f"  FIXED: 0 5-18 * * *")
    
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
tg("✅ <b>Расписание обновлено:</b>\n" +
   "\n".join(f"• {f}" for f in fixes) +
   "\n\n<b>Итог:</b>\n"
   "📡 Парсер Telegram: каждые 60 мин\n"
   "  08:00-21:00 МСК → публикует сразу\n"
   "  21:01-07:59 МСК → в буфер\n"
   "  08:00 МСК → публикует буфер\n\n"
   "📰 RSS: каждый час 08:00-21:00 МСК\n"
   "  Вне расписания → не запускается")
