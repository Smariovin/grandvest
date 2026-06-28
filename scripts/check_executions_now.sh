#!/bin/bash
curl -s -c /tmp/cn_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Последние 5 executions с деталями ошибок
curl -s -b /tmp/cn_ck.txt \
  'http://localhost:5678/rest/executions?limit=5' | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode(),
        method='POST'), timeout=10)

d = json.load(sys.stdin)
items = d.get('data', {})
if isinstance(items, dict): items = items.get('results', [])

report = ['<b>Последние executions:</b>\n']
for ex in items[:5]:
    wf = ex.get('workflowData',{}).get('name', '?')
    status = ex.get('status','?')
    t = str(ex.get('startedAt','?'))[11:16]
    eid = ex.get('id','?')
    icon = '✅' if status=='success' else '❌'
    report.append(f'{icon} {wf} [{t}] {status} id={eid}')

tg('\n'.join(report))
print('\n'.join(report))
" 2>&1

# Берём ID последнего execution и читаем детали
LAST_ID=$(curl -s -b /tmp/cn_ck.txt \
  'http://localhost:5678/rest/executions?limit=5' | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
if items: print(items[0].get('id',''))
" 2>/dev/null)
echo "Last ID: $LAST_ID"

curl -s -b /tmp/cn_ck.txt \
  "http://localhost:5678/rest/executions/${LAST_ID}" | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode(),
        method='POST'), timeout=10)

raw = sys.stdin.read()
try:
    d = json.loads(raw)
    ex = d.get('data', d)
    wf = ex.get('workflowData',{}).get('name','?')
    status = ex.get('status','?')
    result = ex.get('data',{}).get('resultData',{})
    run_data = result.get('runData',{})

    lines = [f'<b>{wf} | {status}</b>\n']
    for node_name, node_runs in run_data.items():
        for nr in (node_runs or []):
            es = nr.get('executionStatus','?')
            err = nr.get('error')
            out = nr.get('data',{}).get('main',[[]])
            cnt = len(out[0]) if out and out[0] else 0
            icon = '✅' if es=='success' else '❌' if err else '⚪'
            line = f'{icon} {node_name}: {es} → {cnt} items'
            if err:
                line += f'\n   ❗ {err.get(\"message\",\"?\")[:100]}'
            lines.append(line)

    tg('\n'.join(lines))
    print('\n'.join(lines))
except Exception as e:
    tg(f'Parse error: {e}')
" 2>&1
