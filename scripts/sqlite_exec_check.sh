#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

# Сначала запускаем вебхук
echo '[]' > /data/published_titles.json
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Складской рынок Подмосковья 2026: вакантность 0.4 процента рекорд за всю историю наблюдений. Ставки аренды складов достигли 14000 рублей за квадратный метр в год. Девелоперы анонсировали строительство 3 миллионов квадратных метров новых площадей до 2028 года по данным NF Group.</div><time datetime=\"2026-06-27T11:00:00+00:00\">11:00</time>"}' \
  && echo "Webhook sent"

sleep 30

# Читаем из SQLite напрямую
python3 << 'PYEOF'
import sqlite3, json, urllib.request, urllib.parse

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Таблицы
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")
tg(f"Tables: {tables}")

# Последние executions
for tbl in tables:
    if 'execution' in tbl.lower():
        try:
            cur.execute(f"SELECT * FROM {tbl} ORDER BY rowid DESC LIMIT 3")
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            print(f"\n=== {tbl} ({len(cols)} cols) ===")
            print(f"Cols: {cols}")
            for row in rows:
                row_dict = dict(zip(cols, row))
                # Показываем ключевые поля
                status = row_dict.get('status', row_dict.get('finished', '?'))
                wf_id = row_dict.get('workflowId', '?')
                t = row_dict.get('startedAt', row_dict.get('createdAt', '?'))
                print(f"  status={status} wf={wf_id} t={str(t)[:16]}")
                
                # Парсим data поле если есть
                data_raw = row_dict.get('data', '')
                if data_raw:
                    try:
                        data = json.loads(data_raw)
                        result = data.get('resultData', {})
                        run_data = result.get('runData', {})
                        for node_name, node_runs in list(run_data.items())[-5:]:
                            for nr in (node_runs or []):
                                es = nr.get('executionStatus', '?')
                                err = nr.get('error')
                                out = nr.get('data', {}).get('main', [[]])
                                cnt = len(out[0]) if out and out[0] else 0
                                icon = '✅' if es == 'success' else '❌' if err else '⚠️'
                                err_msg = err.get('message', '')[:60] if err else ''
                                print(f"    {icon} {node_name}: {es} out={cnt} {err_msg}")
                    except Exception as e:
                        print(f"  data parse error: {e}")
        except Exception as e:
            print(f"{tbl} error: {e}")

conn.close()
PYEOF
