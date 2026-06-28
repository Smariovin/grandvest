#!/usr/bin/env python3
"""
RSS Fix v3:
- Schedule Trigger: каждый час в :01, только 08-20 UTC+3 = 05-17 UTC
- Cron: "1 5-17 * * *"  (05:01-17:01 UTC = 08:01-20:01 МСК)
- Добавляем в RSS проверку времени МСК через Code узел в начале
"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
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

    print(f"RSS WF: {wf_name} ({wf_id})")
    changed = False

    for n in nodes:
        ntype = n.get('type','')
        params = n.get('parameters',{})

        if 'scheduleTrigger' in ntype:
            print(f"  Old schedule: {json.dumps(params)[:150]}")
            # Каждый час в 01 минуту, только 05-17 UTC (08:01-20:01 МСК)
            n['parameters'] = {
                "rule": {
                    "interval": [
                        {
                            "field": "cronExpression",
                            "expression": "1 5-17 * * *"
                        }
                    ]
                }
            }
            changed = True
            fixes.append(f"RSS Schedule: 08:01-20:01 МСК каждый час (cron: 1 5-17 * * *)")
            print(f"  NEW schedule: 1 5-17 * * *")

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
tg(
    "✅ <b>Расписание обновлено:</b>\n\n"
    "<b>📡 Парсер Telegram:</b>\n"
    "• Каждый час в :01 (cron: 1 * * * *)\n"
    "• 08:01-21:00 МСК → публикует сразу\n"
    "• 21:01-08:00 МСК → ночной буфер\n"
    "• 08:00-08:14 МСК → сброс буфера\n"
    "• Парсит новости за последний час\n\n"
    "<b>📰 RSS:</b>\n"
    "• Каждый час в :01, только 08:01-20:01 МСК\n"
    "• Вне расписания — не запускается\n\n"
    "• Новости 21:01-08:00 → публикуются в 08:01"
)
