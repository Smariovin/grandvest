#!/usr/bin/env python3
"""Read RSS execution from SQLite directly"""
import sqlite3, json, urllib.request, urllib.parse, os

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')

def tg(msg):
    if not BOT: print("TG:", msg[:300]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== SQLite RSS Check ===")
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Проверяем структуру таблицы executions
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables: " + str(tables))

# Ищем таблицу с executions
exec_table = None
for t in tables:
    if 'execut' in t.lower():
        cur.execute("PRAGMA table_info(" + t + ")")
        cols = [r[1] for r in cur.fetchall()]
        print("Table " + t + " cols: " + str(cols))
        exec_table = t
        break

if not exec_table:
    tg("No execution table found! Tables: " + str(tables))
    conn.close()
    exit(0)

# Читаем последние RSS executions
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%execut%'")
exec_tables = [r[0] for r in cur.fetchall()]

lines = ["Tables: " + str(exec_tables)]

for tbl in exec_tables:
    cur.execute("PRAGMA table_info(" + tbl + ")")
    cols = [r[1] for r in cur.fetchall()]
    lines.append(tbl + " cols: " + str(cols[:8]))
    
    # Пробуем прочитать последние строки
    try:
        if 'workflowId' in cols or 'workflow_id' in cols:
            wf_col = 'workflowId' if 'workflowId' in cols else 'workflow_id'
            cur.execute("SELECT id, status, " + wf_col + " FROM " + tbl + " ORDER BY id DESC LIMIT 5")
            rows = cur.fetchall()
            for row in rows:
                lines.append("  " + str(row[0]) + " | " + str(row[1]) + " | wf=" + str(row[2]))
    except Exception as e:
        lines.append("  read err: " + str(e)[:50])

conn.close()
tg("<b>SQLite Structure</b>\n\n" + "\n".join(lines[:30]))
print("DONE")
