#!/bin/bash
# Читаем ПОЛНЫЙ код HTTP Request6 из RSS workflow и шлём в TG

BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

echo "=== RSS Workflow - ALL nodes ==="
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows' | python3 -c "
import sys, json
d = json.load(sys.stdin)
for wf in d.get('data', []):
    print(f'ID={wf[\"id\"]} name={wf[\"name\"]!r}')
"

echo ""
echo "=== Finding RSS workflow ID ==="
RSS_ID=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows' | python3 -c "
import sys, json
d = json.load(sys.stdin)
for wf in d.get('data', []):
    if 'RSS' in wf['name'] or 'новост' in wf['name'].lower() or 'сбор' in wf['name'].lower():
        print(wf['id'])
        break
")
echo "RSS ID: $RSS_ID"

echo ""
echo "=== HTTP Request6 FULL params ==="
curl -s -b /tmp/ck.txt "http://localhost:5678/rest/workflows/${RSS_ID}" | python3 << 'PYEOF'
import sys, json, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])
wf_name = wf.get('name', '?')
wf_id = wf.get('id', '?')

print(f'WF: {wf_name} ({wf_id})')
print(f'Nodes: {len(nodes)}')

report = [f'<b>RSS WF: {wf_name}</b>']

for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '').split('.')[-1]
    params = n.get('parameters', {})
    url = params.get('url', '')
    
    # Показываем HTTP Request узлы
    if ntype == 'httpRequest' and ('openrouter' in url.lower() or 'HTTP Request6' in name):
        print(f'\n=== NODE: {name} ===')
        print(f'URL: {url}')
        
        # Все ключи параметров
        print(f'All param keys: {list(params.keys())}')
        
        # jsonBody
        jb = params.get('jsonBody', 'NOT SET')
        print(f'jsonBody type: {type(jb).__name__}')
        print(f'jsonBody value: {str(jb)!r}')
        
        # body
        body = params.get('body', 'NOT SET')
        print(f'body type: {type(body).__name__}')
        print(f'body value: {str(body)[:200]!r}')
        
        # specifyBody
        print(f'specifyBody: {params.get("specifyBody", "NOT SET")}')
        print(f'bodyContentType: {params.get("bodyContentType", "NOT SET")}')
        print(f'sendBody: {params.get("sendBody", "NOT SET")}')
        
        # headerParameters
        headers = params.get('headerParameters', {}).get('parameters', [])
        for h in headers:
            print(f'Header: {h.get("name")}: {str(h.get("value",""))[:50]}')
        
        report.append(f'\n<b>{name}</b>')
        report.append(f'jsonBody: {str(jb)[:300]!r}')
        report.append(f'specifyBody: {params.get("specifyBody","?")}')
        report.append(f'body: {str(body)[:200]!r}')

tg('\n'.join(report))
print('\nSent to TG')
PYEOF
