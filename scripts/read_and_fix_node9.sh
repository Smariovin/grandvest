#!/bin/bash
set -e

echo "=== Step 1: Login to n8n ==="
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Login:', 'OK' if d.get('data') else 'FAIL', d.get('message',''))"

echo ""
echo "=== Step 2: Read node 9 via API ==="
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
nodes = d.get('nodes', [])
print(f'Total nodes: {len(nodes)}')
for n in nodes:
    name = n.get('name','')
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    if '9.' in name or 'Отправка' in name:
        print(f'NODE 9: {name!r}')
        print(f'Type: {n.get(\"type\",\"?\")}')
        print(f'Code ({len(code)} chars):')
        print(code[:500])
        print()
        print('Has grandvest-publisher:', 'grandvest-publisher' in code)
        print('Has sendPhoto:', 'sendPhoto' in code)
        print('Has api.telegram.org:', 'api.telegram.org' in code)
"

echo ""
echo "=== Step 3: Check SQLite directly ==="
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()
cur.execute(\"SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'\")
nodes = json.loads(cur.fetchone()[0])
for n in nodes:
    name = n.get('name','')
    code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
    if 'Отправка' in name or '9.' in name:
        print(f'SQLite NODE 9: {name!r}')
        print(f'Code ({len(code)} chars): {code[:300]}')
        print(f'Has grandvest-publisher: {\"grandvest-publisher\" in code}')
        print(f'Has sendPhoto: {\"sendPhoto\" in code}')
conn.close()
"
