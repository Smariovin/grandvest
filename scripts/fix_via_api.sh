#!/bin/bash
GH_PAT="${GH_PAT}"

echo "=== Login ==="
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /tmp/login_resp.json
cat /tmp/login_resp.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('Login OK' if d.get('data') else f'FAIL: {d}')"

echo ""
echo "=== Get workflow ==="
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' > /tmp/wf.json

python3 -c "
import json, os, sys

GH_PAT = os.environ.get('GH_PAT','')
print(f'GH_PAT available: {bool(GH_PAT)}, length: {len(GH_PAT)}')

with open('/tmp/wf.json') as f:
    resp = json.load(f)

# n8n REST API возвращает {data: {...workflow...}}
wf = resp.get('data', resp)
nodes = wf.get('nodes', [])
print(f'Nodes in workflow: {len(nodes)}')

# Показываем узел 9
for n in nodes:
    name = n.get('name','')
    code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
    if 'Отправка' in name or '9.' in name:
        print(f'\nNODE 9: {name!r}')
        print(f'Code preview: {code[:200]!r}')
        print(f'grandvest-publisher: {\"grandvest-publisher\" in code}')
        print(f'api.telegram.org: {\"api.telegram.org\" in code}')

# ПАТЧ: заменяем код узла 9
NEW_CODE = f'''// Отправка в Telegram через GitHub Actions (api.telegram.org заблокирован с РФ)
const postText = \$(\"8. Подготовка данных поста\").first().json.tg_post;
const imageUrl = \$(\"HTTP Request \\u2014 fal.ai\").first().json.images?.[0]?.url || \"\";

if (!postText || postText.length < 10) {{
  throw new Error(\"tg_post пустой: \" + JSON.stringify(postText));
}}

console.log(\"Post:\", postText.length, \"chars, image:\", !!imageUrl);

const r = await this.helpers.httpRequest({{
  method: \"POST\",
  url: \"https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches\",
  headers: {{
    \"Authorization\": \"token {GH_PAT}\",
    \"Content-Type\": \"application/json\",
    \"Accept\": \"application/vnd.github+json\"
  }},
  body: JSON.stringify({{
    ref: \"main\",
    inputs: {{ message: postText, image_url: imageUrl }}
  }})
}});

console.log(\"Dispatched to GitHub Actions OK\");
return [{{ json: {{ ok: true, len: postText.length }} }}];'''

patched = False
for n in nodes:
    name = n.get('name','')
    if 'Отправка' in name or '9.' in name:
        n['parameters']['jsCode'] = NEW_CODE
        n['parameters'].pop('code', None)
        patched = True
        print(f'\nPATCHED: {name!r}')

if patched:
    # Сохраняем через n8n REST API
    wf['nodes'] = nodes
    with open('/tmp/wf_patched.json','w') as f:
        json.dump(wf, f, ensure_ascii=False)
    print('Saved patched workflow to /tmp/wf_patched.json')
else:
    print('NODE 9 NOT FOUND!')
    for n in nodes:
        print(f'  {n.get(\"name\",\"?\")!r}')
"

echo ""
echo "=== PUT patched workflow ==="
curl -s -b /tmp/ck.txt \
  -X PUT http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ \
  -H 'Content-Type: application/json' \
  -d @/tmp/wf_patched.json \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
wf = d.get('data',d)
nodes = wf.get('nodes',[])
print(f'PUT response nodes: {len(nodes)}')
for n in nodes:
    name = n.get('name','')
    if 'Отправка' in name or '9.' in name:
        code = n.get('parameters',{}).get('jsCode','')
        print(f'Node 9 after PUT: {name!r}')
        print(f'Has grandvest-publisher: {\"grandvest-publisher\" in code}')
        print(f'Code: {code[:100]!r}')
"

echo ""
echo "=== Activate workflow ==="
curl -s -b /tmp/ck.txt \
  -X POST http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ/activate \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Activate:', d.get('data',{}).get('active','?'))"

echo "=== DONE ==="
