#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
WORKING_PAT="${WORKING_PAT}"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

# Сначала смотрим ТОЧНУЮ ошибку
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

EXEC_DETAILS=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=5')

python3 << PYEOF
import json, os

raw = '''$EXEC_DETAILS'''
try:
    d = json.loads(raw)
    items = d.get('data',{})
    if isinstance(items,dict): items = items.get('results',[])
    for ex in items[:5]:
        status = ex.get('status','?')
        wf = ex.get('workflowData',{}).get('name','?')
        t = str(ex.get('startedAt','?'))[11:16]
        eid = ex.get('id','?')
        print(f"[{status}] {wf} [{t}] id={eid}")
except Exception as e:
    print(f"Parse error: {e}")
    print(raw[:200])
PYEOF

# Получаем ПОЛНУЮ ошибку последнего execution
LAST_ID=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=10' | \
  python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
for ex in items:
    if ex.get('status')=='error':
        print(ex.get('id',''))
        break
")
echo "Last error ID: $LAST_ID"

# Читаем детальный execution
FULL=$(curl -s -b /tmp/ck.txt "http://localhost:5678/rest/executions/${LAST_ID}")
echo "$FULL" | python3 -c "
import sys,json,urllib.request,urllib.parse
BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'
def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000]}).encode(),
        method='POST'),timeout=10)

d=json.load(sys.stdin)
ex=d.get('data',d)
result=ex.get('data',{}).get('resultData',{})
run_data=result.get('runData',{})
lines=['<b>EXACT ERRORS:</b>']
for node,runs in run_data.items():
    for r in (runs or []):
        err=r.get('error')
        if err:
            lines.append(f'❌ <b>{node}</b>')
            lines.append(f'Type: {err.get(\"name\",\"?\")}')
            lines.append(f'Msg: {err.get(\"message\",\"?\")[:200]}')
            desc=err.get(\"description\",\"\")
            if desc: lines.append(f'Desc: {desc[:100]}')
tg('\n'.join(lines) if len(lines)>1 else 'No errors found in runData')
print('\n'.join(lines))
" 2>&1

# Теперь перестраиваем проблемный узел
docker stop n8n && sleep 3

python3 << PYEOF
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT','')
print(f"PAT: {PAT[:15]}...")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Читаем все узлы Парсера Telegram
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
nodes_raw = cur.fetchone()[0]
nodes = json.loads(nodes_raw)

print("Current nodes:")
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','').split('.')[-1]
    params = n.get('parameters',{})
    code = params.get('jsCode',params.get('code',''))
    url = params.get('url','')
    print(f"  [{ntype}] {name!r} code={len(code)} url={url[:50]}")

# Узел "1. Парсинг HTML Telegram" — смотрим что он выдаёт
for n in nodes:
    name = n.get('name','')
    if '1.' in name or 'Парсинг' in name:
        code = n.get('parameters',{}).get('jsCode',n.get('parameters',{}).get('code',''))
        print(f"\nNode 1 code ({len(code)} chars):")
        print(code[:600])
        break

conn.close()
PYEOF

docker start n8n
