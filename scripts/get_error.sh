#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Получаем ID последнего failed execution
EXEC_ID=$(curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=5' | \
  python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
for ex in items:
    if ex.get('status')=='error':
        print(ex['id'])
        break
")
echo "Last error execution ID: $EXEC_ID"

# Читаем полные данные этого execution
curl -s -b /tmp/ck.txt \
  "http://localhost:5678/rest/executions/${EXEC_ID}" | \
python3 << 'PYEOF'
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(msg):
    url=f'https://api.telegram.org/bot{BOT}/sendMessage'
    data=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)

raw = sys.stdin.read()
try:
    d = json.loads(raw)
except:
    tg(f'JSON parse error: {raw[:200]}')
    exit()

ex = d.get('data', d)
wf = ex.get('workflowData',{}).get('name','?')
status = ex.get('status','?')
data = ex.get('data', {})
result = data.get('resultData', {})
run_data = result.get('runData', {})
err_top = result.get('error', {})

lines = [f'<b>Execution: {wf} | {status}</b>']

if err_top:
    lines.append(f'TOP ERROR: {err_top.get("message","?")}')
    lines.append(f'Node: {err_top.get("node",{}).get("name","?")}')

for node_name, node_runs in run_data.items():
    for nr in (node_runs or []):
        es = nr.get('executionStatus','?')
        err = nr.get('error')
        out = nr.get('data',{}).get('main',[[]])
        cnt = len(out[0]) if out and out[0] else 0
        icon = '✅' if es=='success' else '❌' if err else '⚠️'
        
        line = f'{icon} {node_name}: {es} → {cnt} items'
        if err:
            emsg = err.get('message','?')
            etype = err.get('name','?')
            line += f'\n   {etype}: {emsg[:120]}'
            # Stack trace first line
            stack = err.get('stack','')
            if stack:
                line += f'\n   Stack: {stack.split(chr(10))[0][:80]}'
        lines.append(line)

msg = '\n'.join(lines)
print(msg)
tg(msg)
PYEOF
