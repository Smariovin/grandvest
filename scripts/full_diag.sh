#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

echo "=== ALL WORKFLOWS ==="
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows' | \
python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', [])
print(f'Total workflows: {len(items)}')
for wf in items:
    print(f'  ID={wf[\"id\"]} name={wf[\"name\"]!r} active={wf[\"active\"]}')
"

echo ""
echo "=== RSS WORKFLOW NODES ==="
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows/SIPnV2mqmgMqUkLb' | \
python3 -c "
import sys, json
d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])
print(f'RSS Workflow nodes: {len(nodes)}')
for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '').split('.')[-1]
    params = n.get('parameters', {})
    url = params.get('url', '')
    jb = params.get('jsonBody', params.get('body', ''))
    code = params.get('jsCode', params.get('code', ''))
    print(f'  NODE: {name!r} [{ntype}]')
    if url: print(f'    url: {url[:80]}')
    if jb: print(f'    jsonBody ({type(jb).__name__}, {len(str(jb))}): {str(jb)[:200]!r}')
    if code: print(f'    code ({len(code)}): {code[:100]!r}')
    print()
" 2>&1 | tee /tmp/rss_nodes.txt

# Отправляем в TG
CONTENT=$(cat /tmp/rss_nodes.txt | head -60)
curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=🔍 RSS Workflow nodes:
$CONTENT" > /dev/null

echo "=== TELEGRAM PARSER HTTP REQUEST nodes ==="
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
import sys, json
d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])
for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '').split('.')[-1]
    params = n.get('parameters', {})
    if ntype == 'httpRequest':
        url = params.get('url', '')
        jb = params.get('jsonBody', '')
        print(f'HTTP NODE: {name!r}')
        print(f'  url: {url[:80]}')
        print(f'  jsonBody type: {type(jb).__name__}')
        print(f'  jsonBody len: {len(str(jb))}')
        print(f'  jsonBody: {str(jb)[:300]!r}')
        print(f'  ALL KEYS: {list(params.keys())}')
        print()
" 2>&1

echo "DONE"
