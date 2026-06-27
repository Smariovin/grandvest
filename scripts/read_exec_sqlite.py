#!/usr/bin/env python3
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

# Ищем таблицу с executions
exec_table = None
for t in tables:
    if 'execution' in t.lower():
        exec_table = t
        break

if not exec_table:
    tg(f"No execution table! Tables: {tables}")
    conn.close()
    exit()

# Читаем последний успешный execution Парсера Telegram
cur.execute(f"PRAGMA table_info({exec_table})")
cols = [r[1] for r in cur.fetchall()]
print(f"Columns: {cols}")

# Читаем последние executions
cur.execute(f"SELECT * FROM {exec_table} ORDER BY rowid DESC LIMIT 5")
rows = cur.fetchall()

report = [f'<b>Last executions ({exec_table}):</b>']
for row in rows:
    rd = dict(zip(cols, row))
    status = rd.get('status', rd.get('finished', '?'))
    wf_id = rd.get('workflowId', '?')
    t = str(rd.get('startedAt', rd.get('createdAt', '?')))[:16]
    report.append(f'{status} | wf={wf_id} | {t}')
    
    # Читаем данные если есть
    data_raw = rd.get('data', '')
    if data_raw and status in ('success', True, 1):
        try:
            data = json.loads(data_raw)
            run_data = data.get('resultData', {}).get('runData', {})
            for node_name, node_runs in list(run_data.items())[:10]:
                for nr in (node_runs or []):
                    out = nr.get('data', {}).get('main', [[]])
                    cnt = len(out[0]) if out and out[0] else 0
                    if cnt > 0 and out[0]:
                        first = out[0][0].get('json', {})
                        # Ищем поля с текстом новости
                        text_fields = {k: str(v)[:60] for k,v in first.items() 
                                      if any(x in k.lower() for x in ['text','title','content','message','post'])}
                        if text_fields:
                            report.append(f'  {node_name}: {text_fields}')
        except Exception as e:
            report.append(f'  parse error: {e}')
    break  # Только первый

conn.close()
msg = '\n'.join(report)
print(msg)
tg(msg)
