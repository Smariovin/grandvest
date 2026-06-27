#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ft_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Читаем execution 1535 (последний успешный) и смотрим что выходит из каждого узла
curl -s -b /tmp/ft_ck.txt 'http://localhost:5678/rest/executions/1535' | \
python3 << 'PYEOF'
import sys, json, subprocess, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

d = json.load(sys.stdin)
ex = d.get('data', d)
result = ex.get('data', {}).get('resultData', {})
run_data = result.get('runData', {})

report = ['<b>Execution 1535 — данные узлов:</b>\n']

KEY_NODES = ['1. Парсинг HTML', '2. Дедупликац', '6. Извлечение', '8. Подготовка', 'HTTP Request — генерац']

for node_name, node_runs in run_data.items():
    show = any(k in node_name for k in KEY_NODES)
    if not show:
        continue
    for nr in (node_runs or []):
        out = nr.get('data', {}).get('main', [[]])
        if out and out[0]:
            first = out[0][0].get('json', {})
            report.append(f'<b>{node_name}:</b>')
            # Показываем все поля
            for k, v in list(first.items())[:8]:
                val_str = str(v)[:80]
                report.append(f'  {k}: {val_str!r}')
            report.append('')

msg = '\n'.join(report)
print(msg)
tg(msg)
PYEOF
