#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/rep_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

python3 << 'PYEOF'
import sqlite3, json, urllib.request, urllib.parse, subprocess, re, datetime

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
LOG_FILE = '/data/published_log.json'

def tg(m, parse_mode='HTML'):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': parse_mode, 'disable_web_page_preview': True}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e: print(f"TG error: {e}")

# 1. Читаем лог публикаций
logs = []
try:
    with open(LOG_FILE) as f:
        logs = json.load(f)
    print(f"Log entries: {len(logs)}")
except Exception as e:
    print(f"Log error: {e}")

# Фильтруем за последний час (10:01-11:00)
msk_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
print(f"Current MSK: {msk_now.strftime('%H:%M')}")

# 2. Читаем последние executions из n8n
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Ищем таблицу executions
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")

exec_table = None
for t in tables:
    if 'execution' in t.lower():
        cur.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in cur.fetchall()]
        if 'data' in cols or 'workflowData' in cols:
            exec_table = t
            print(f"Using table: {t}, cols: {cols[:10]}")
            break

report_lines = [f'📊 <b>Отчёт парсинга 10:01–11:00 МСК</b>\n']
published_items = []
rejected_items = []
buffered_items = []

if exec_table:
    cur.execute(f"SELECT * FROM {exec_table} ORDER BY rowid DESC LIMIT 20")
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    
    print(f"Executions found: {len(rows)}")
    
    for row in rows:
        rd = dict(zip(cols, row))
        status = rd.get('status', rd.get('finished', ''))
        wf_id = rd.get('workflowId', rd.get('workflowid', ''))
        started = str(rd.get('startedAt', rd.get('startTime', rd.get('createdAt', ''))))[:16]
        
        print(f"  Exec: status={status} wf={wf_id} t={started}")
        
        data_raw = rd.get('data', '')
        if not data_raw:
            continue
            
        try:
            data = json.loads(data_raw)
            result = data.get('resultData', {})
            run_data = result.get('runData', {})
            
            # Анализируем каждый узел
            for node_name, node_runs in run_data.items():
                for nr in (node_runs or []):
                    es = nr.get('executionStatus', '')
                    out = nr.get('data', {}).get('main', [[]])
                    cnt = len(out[0]) if out and out[0] else 0
                    err = nr.get('error', {})
                    
                    # Парсинг HTML - что пришло
                    if '1.' in node_name or 'Парсинг' in node_name:
                        if cnt > 0 and out[0]:
                            for item in out[0]:
                                j = item.get('json', {})
                                title = j.get('title', j.get('text', ''))[:80]
                                source = j.get('source', j.get('channel', '?'))
                                if title:
                                    published_items.append({
                                        'title': title,
                                        'source': source,
                                        'time': started,
                                        'node': node_name
                                    })
                    
                    # Фильтр оценки - что отфильтровалось
                    if 'фильтр' in node_name.lower() or 'filter' in node_name.lower():
                        if cnt == 0:
                            # Читаем что было на входе
                            input_data = nr.get('inputOverride', {})
                            rejected_items.append({
                                'node': node_name,
                                'time': started,
                                'reason': 'score < 4 (низкая релевантность)'
                            })
                    
                    # Дедупликация - что заблокировала
                    if 'дедупликац' in node_name.lower() or '2.' in node_name:
                        if cnt == 0 and es == 'success':
                            rejected_items.append({
                                'node': 'Дедупликация',
                                'time': started,
                                'reason': 'новость уже публиковалась ранее'
                            })
        except Exception as e:
            print(f"  Parse error: {e}")

conn.close()

# 3. Читаем published_log.json
recent_published = []
for entry in logs:
    t = entry.get('time_msk', entry.get('time', ''))
    if '28.06' in t or '10:' in t or '11:' in t:
        recent_published.append(entry)

# 4. Формируем отчёт
if recent_published:
    report_lines.append(f'✅ <b>Опубликовано ({len(recent_published)}):</b>')
    for e in recent_published:
        ch = e.get('channel', e.get('source_name', '?'))
        t = e.get('time_msk', e.get('time', '?'))
        src_url = e.get('channel_url', e.get('source_url', ''))
        parser = e.get('parser', 'RSS')
        preview = e.get('preview', '')[:60]
        line = f'• {t} | {parser} | @{ch}'
        if src_url:
            line += f'\n  🔗 {src_url}'
        if preview:
            line += f'\n  💬 {preview}...'
        report_lines.append(line)
else:
    report_lines.append('✅ <b>Опубликовано:</b> нет данных в логе')
    
    # Пробуем из executions
    if published_items:
        for item in published_items[:5]:
            report_lines.append(f'• {item["time"]} | {item["source"]} | {item["title"]}')

report_lines.append('')

# Причины отклонения
if rejected_items:
    report_lines.append(f'❌ <b>Не прошли отбор ({len(rejected_items)}):</b>')
    reasons = {}
    for r in rejected_items:
        reason = r.get('reason', '?')
        reasons[reason] = reasons.get(reason, 0) + 1
    for reason, count in reasons.items():
        report_lines.append(f'• {count}x — {reason}')
else:
    report_lines.append('❌ <b>Отклонённые:</b> нет данных')

report_lines.append('')
report_lines.append(f'🕐 Отчёт сформирован: {msk_now.strftime("%d.%m.%Y %H:%M")} МСК')

msg = '\n'.join(report_lines)
print(msg)
tg(msg)
PYEOF
