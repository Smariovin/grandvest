#!/usr/bin/env python3
"""Читаем последние executions из SQLite и анализируем узлы"""
import sqlite3, json, urllib.request, urllib.parse

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'
    }).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Структура таблицы
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]

exec_table = None
for t in tables:
    if 'execution' in t.lower() and 'annotation' not in t.lower():
        cur.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in cur.fetchall()]
        if any('data' in c.lower() for c in cols):
            exec_table = t
            print(f"Exec table: {t}, cols: {cols[:8]}")
            break

if not exec_table:
    tg(f"❌ Нет таблицы executions. Tables: {tables}")
    conn.close()
    exit()

# Читаем последние 5 executions
cur.execute(f"SELECT * FROM {exec_table} ORDER BY rowid DESC LIMIT 5")
cols = [c[0] for c in cur.description]
rows = cur.fetchall()

for row in rows:
    rd = dict(zip(cols, row))
    status = rd.get('status', rd.get('finished', '?'))
    wf_id = rd.get('workflowId', '?')
    t_val = str(rd.get('startedAt', rd.get('createdAt', '?')))[:16]
    data_raw = rd.get('data', '')
    
    print(f"\nExec: status={status} wf={wf_id} t={t_val}")
    
    if not data_raw:
        continue
    
    try:
        data = json.loads(data_raw)
        run_data = data.get('resultData', {}).get('runData', {})
        
        lines = [f'<b>Exec {t_val} | {status}</b>']
        
        for node_name, node_runs in run_data.items():
            for nr in (node_runs or []):
                es = nr.get('executionStatus', '?')
                err = nr.get('error')
                out = nr.get('data', {}).get('main', [[]])
                cnt = len(out[0]) if out and out[0] else 0
                
                icon = '✅' if es == 'success' else '❌' if err else '⚪'
                line = f'{icon} {node_name}: {cnt} items'
                
                if err:
                    msg = str(err.get('message', '?'))[:100]
                    line += f'\n   ❗ {msg}'
                
                if es == 'success' and cnt == 0 and not err:
                    line += ' ← ФИЛЬТР ЗАБЛОКИРОВАЛ'
                    # Смотрим что Claude ответил
                    if 'Claude' in node_name or 'оценка' in node_name.lower():
                        inp = nr.get('data', {}).get('main', [[]])
                        if inp and inp[0]:
                            claude_out = inp[0][0].get('json', {})
                            choices = claude_out.get('choices', [])
                            if choices:
                                content = choices[0].get('message', {}).get('content', '')
                                line += f'\n   Claude ответ: {content[:150]}'
                
                lines.append(line)
                print(f"  {line[:80]}")
        
        tg('\n'.join(lines))
        
    except Exception as e:
        print(f"  Parse error: {e}")

conn.close()
