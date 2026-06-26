#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

echo "=== Last 5 executions via n8n API ==="
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=10&includeData=true' | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

d = json.load(sys.stdin)
execs = d.get('data', {})
if isinstance(execs, dict):
    items = execs.get('results', execs.get('data', []))
elif isinstance(execs, list):
    items = execs
else:
    items = []

print(f'Executions found: {len(items)}')

report = ['<b>Last executions:</b>']
for ex in items[:8]:
    eid = ex.get('id','?')
    wname = ex.get('workflowData',{}).get('name', ex.get('workflowId','?'))
    status = ex.get('status','?')
    started = str(ex.get('startedAt','?'))[11:16]
    
    # Ищем ошибку
    err = ''
    data = ex.get('data', {})
    if data:
        result = data.get('resultData', {})
        run_data = result.get('runData', {})
        last_node = list(run_data.keys())[-1] if run_data else '?'
        # Ошибка последнего узла
        for node_name, node_runs in run_data.items():
            for r in (node_runs or []):
                if r.get('error'):
                    err = f\" ERR '{node_name}': {r['error'].get('message','?')[:60]}\"
    else:
        last_node = '?'
    
    icon = '✅' if status == 'success' else '❌' if status == 'error' else '⚠️'
    line = f'{icon} {wname} [{started}]{err}'
    report.append(line)
    print(line)

tg('\n'.join(report))
" 2>&1

echo ""
echo "=== Webhook test ==="
# Сбрасываем дедупликацию
echo '[]' > /data/published_titles.json
echo "Dedup reset"

# Отправляем тест
RESP=$(curl -s -X POST http://localhost:5678/webhook/telegram-parser \
    -H 'Content-Type: application/json' \
    -d '{
        "channel": "CRERussia",
        "html": "<div class=\"tgme_widget_message_text js-message_text\">Вакантность офисов класса А в Москве упала до 7.8% по данным CBRE за первое полугодие 2026 года. Ставки аренды в ЦАО достигли 48000 рублей за квадратный метр в год. IT-компании обеспечили 34% от общего объема сделок аренды.</div><time datetime=\"2026-06-26T10:00:00+00:00\">10:00</time>"
    }')
echo "Webhook: $RESP"

sleep 60

echo ""
echo "=== Executions after test ==="
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=5&includeData=true' | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

d = json.load(sys.stdin)
execs = d.get('data', {})
if isinstance(execs, dict):
    items = execs.get('results', [])
elif isinstance(execs, list):
    items = execs
else:
    items = []

report = ['<b>After test executions:</b>']
for ex in items[:5]:
    wname = ex.get('workflowData',{}).get('name', ex.get('workflowId','?'))
    status = ex.get('status','?')
    started = str(ex.get('startedAt','?'))[11:16]
    data = ex.get('data', {})
    
    err_details = []
    if data:
        result = data.get('resultData', {})
        run_data = result.get('runData', {})
        nodes_done = list(run_data.keys())
        
        # Находим ошибку
        for node_name, node_runs in run_data.items():
            for r in (node_runs or []):
                if r.get('error'):
                    e = r['error']
                    err_details.append(f\"  ❌ Node '{node_name}': {e.get('message','?')[:100]}\")
                    # Детали входных данных
                    inp = r.get('inputOverride', r.get('data',{}).get('main',[[]])[0] if r.get('data',{}).get('main') else [])
                    if inp:
                        err_details.append(f\"  Input: {str(inp)[:100]}\")
    
    icon = '✅' if status == 'success' else '❌'
    line = f'{icon} {wname} [{started}] status={status}'
    if err_details:
        line += '\n' + '\n'.join(err_details)
    report.append(line)
    print(line)

tg('\n'.join(report))
print('Report sent to TG')
" 2>&1
