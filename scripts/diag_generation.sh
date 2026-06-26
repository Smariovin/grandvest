#!/bin/bash
# Читаем точную структуру узла генерации через n8n API
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
import sys, json

d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])

for n in nodes:
    name = n.get('name', '')
    if 'генерац' in name.lower() or name == 'HTTP Request — генерация поста':
        params = n.get('parameters', {})
        print(f'NODE: {name!r}')
        print(f'ALL PARAM KEYS: {list(params.keys())}')
        print()
        # Печатаем КАЖДЫЙ параметр
        for k, v in params.items():
            val_str = str(v)
            print(f'  {k}: ({type(v).__name__}) {val_str[:300]!r}')
            print()
"
