#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

echo "=== Latest execution with FULL details ==="
# Сбрасываем дедупликацию
echo '[]' > /data/published_titles.json
echo "Dedup reset"

# Отправляем тест
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Офисная недвижимость Москвы 2026: вакантность класса А упала до 7.8 процента по данным CBRE. Ставки в ЦАО достигли 48000 рублей за квадратный метр в год. IT-компании обеспечили 34 процента сделок.</div><time datetime=\"2026-06-26T10:00:00+00:00\">10:00</time>"}' &

sleep 30

# Читаем детали последнего execution
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=3&includeData=true' | \
python3 -c "
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

for ex in items[:2]:
    wf = ex.get('workflowData', {}).get('name', ex.get('workflowId','?'))
    status = ex.get('status', '?')
    data = ex.get('data', {})
    
    result = data.get('resultData', {})
    run_data = result.get('runData', {})
    
    report = [f'<b>WF: {wf} | {status}</b>']
    
    for node_name, node_runs in run_data.items():
        for nr in (node_runs or []):
            has_err = bool(nr.get('error'))
            exec_status = nr.get('executionStatus', '?')
            icon = '✅' if exec_status == 'success' else '❌' if has_err else '⚠️'
            
            line = f'{icon} {node_name}: {exec_status}'
            
            if has_err:
                err = nr['error']
                line += f\" | ERR: {err.get('message','?')[:80]}\"
            
            # Данные выхода узла
            output = nr.get('data', {}).get('main', [[]])
            if output and output[0]:
                first = output[0][0] if output[0] else {}
                jdata = first.get('json', {})
                if jdata:
                    keys = list(jdata.keys())[:5]
                    line += f\" | out: {keys}\"
            
            report.append(line)
            print(line)
    
    tg('\n'.join(report))
print('Sent to TG')
" 2>&1
