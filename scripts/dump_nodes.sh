#!/bin/bash
# Логинимся и читаем workflow
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Получаем workflow и выводим имена узлов и первые строки кода
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
import sys, json
d = json.load(sys.stdin)
nodes = d.get('nodes', [])
print(f'Total nodes: {len(nodes)}')
for n in nodes:
    name = n.get('name','')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code',''))
    ntype = n.get('type','')
    print(f'\n=== {name} ===')
    print(f'TYPE: {ntype}')
    if code:
        print(f'CODE ({len(code)} chars):')
        lines = code.split('\n')
        for line in lines[:8]:
            print('  ' + line)
        if len(lines) > 8:
            print(f'  ... [{len(lines)-8} more lines]')
"
