#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Сбрасываем дедуп
echo '[]' > /data/published_titles.json

# Отправляем тест и ждём
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Тестовая новость о рынке недвижимости Москвы 2026 для проверки пайплайна системы публикации постов в канал Grandvest</div><time datetime=\"2026-06-26T11:00:00+00:00\">11:00</time>"}' > /dev/null &

sleep 40

# Получаем execution с ПОЛНЫМИ деталями каждого узла
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=2&includeData=true' | \
python3 << 'PYEOF'
import sys, json, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

d = json.load(sys.stdin)
items = d.get('data', {})
if isinstance(items, dict): items = items.get('results', [])

for ex in items[:1]:
    wf = ex.get('workflowData',{}).get('name','?')
    status = ex.get('status','?')
    data = ex.get('data',{})
    result = data.get('resultData',{}) if data else {}
    run_data = result.get('runData',{})
    
    lines = [f'<b>{wf} | {status}</b>']
    
    for node_name, node_runs in run_data.items():
        for nr in (node_runs or []):
            exec_status = nr.get('executionStatus','?')
            err = nr.get('error',{}) or {}
            err_msg = err.get('message','') if err else ''
            
            # Выходные данные
            out = nr.get('data',{}).get('main',[[]])
            out_items = out[0] if out and out[0] else []
            out_count = len(out_items)
            
            # Первый выходной элемент
            first_out = ''
            if out_items:
                j = out_items[0].get('json',{})
                first_out = str(j)[:80]
            
            icon = '✅' if exec_status == 'success' else '❌' if exec_status == 'error' else '⏸️'
            line = f'{icon} {node_name}: {exec_status} out={out_count}'
            if err_msg: line += f'\n   ERR: {err_msg[:80]}'
            if first_out and not err_msg: line += f'\n   → {first_out}'
            lines.append(line)
    
    msg = '\n'.join(lines)
    print(msg)
    tg(msg)
PYEOF
