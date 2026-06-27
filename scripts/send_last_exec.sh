#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Берём последний execution и читаем детально каждый узел
LAST_ID=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=5' | \
python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
# Берём первый не-тривиальный (не 72ms)
for ex in items:
    if ex.get('stoppedAt') and ex.get('startedAt'):
        import datetime
        try:
            start=datetime.datetime.fromisoformat(ex['startedAt'].replace('Z','+00:00'))
            stop=datetime.datetime.fromisoformat(ex['stoppedAt'].replace('Z','+00:00'))
            dur=(stop-start).total_seconds()
            if dur > 1:
                print(ex['id'])
                break
        except:
            print(ex['id']); break
" 2>/dev/null)

echo "Reading execution: $LAST_ID"

curl -s -b /tmp/ck.txt "http://localhost:5678/rest/executions/${LAST_ID}" | \
python3 << 'PYEOF'
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(m):
    url=f'https://api.telegram.org/bot{BOT}/sendMessage'
    data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)

raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception as e:
    tg(f'Parse error: {e}')
    exit()

ex = d.get('data', d)
wf = ex.get('workflowData',{}).get('name','?')
status = ex.get('status','?')
t = str(ex.get('startedAt','?'))[11:16]
result = ex.get('data',{}).get('resultData',{})
run_data = result.get('runData',{})

lines = [f'<b>{wf} | {status} | {t}</b>\n']

for node_name, node_runs in run_data.items():
    for nr in (node_runs or []):
        es = nr.get('executionStatus','?')
        err = nr.get('error')
        out = nr.get('data',{}).get('main',[[]])
        cnt = len(out[0]) if out and out[0] else 0

        icon = '✅' if es == 'success' else '❌' if err else '⚠️'
        line = f'{icon} {node_name}: {es} → {cnt} items'

        if err:
            line += f'\n   ERR: {err.get("message","?")[:100]}'

        # Показываем данные на выходе первого успешного узла
        if cnt > 0 and out[0]:
            first = out[0][0].get('json',{})
            keys = list(first.keys())[:5]
            vals = {k: str(v)[:30] for k,v in list(first.items())[:3]}
            line += f'\n   out: {vals}'

        lines.append(line)

msg = '\n'.join(lines)
tg(msg)
print(msg)
PYEOF
