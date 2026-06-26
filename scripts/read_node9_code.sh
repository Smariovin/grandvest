#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
GH_PAT="${GH_PAT}"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

python3 << PYEOF
import subprocess, json, urllib.request, urllib.parse, os, re, sqlite3

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')
DB = '/opt/n8n/n8n_data/database.sqlite'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

# Читаем узел 9 напрямую из SQLite
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)

node9_code = ''
node9_name = ''
for n in nodes:
    name = n.get('name', '')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code', ''))
    if 'Отправка' in name and 'Telegram' in name:
        node9_code = code
        node9_name = name
        break
    if '9.' in name and 'Telegram' in name:
        node9_code = code
        node9_name = name
        break

print(f"Node9 name: {node9_name!r}")
print(f"Node9 code ({len(node9_code)} chars):")
print(node9_code)

# Ищем токен в коде
tokens = re.findall(r'ghp_[A-Za-z0-9]+', node9_code)
print(f"\nTokens found in node9: {tokens}")

# Проверяем каждый токен
for tok in tokens:
    try:
        req = urllib.request.Request(
            'https://api.github.com/user',
            headers={'Authorization': f'token {tok}'}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
            print(f"Token {tok[:15]}... -> valid, user: {d['login']}")
    except Exception as e:
        print(f"Token {tok[:15]}... -> INVALID: {e}")

# Теперь заменяем токен на рабочий и сохраняем
if GH_PAT and GH_PAT not in node9_code:
    print(f"\nReplacing old token with working PAT...")
    new_code = node9_code
    for tok in tokens:
        new_code = new_code.replace(tok, GH_PAT)
    
    # Обновляем в nodes
    for n in nodes:
        name = n.get('name', '')
        if 'Отправка' in name and 'Telegram' in name:
            n['parameters']['jsCode'] = new_code
            print(f"Updated node: {name}")
        elif '9.' in name and 'Telegram' in name:
            n['parameters']['jsCode'] = new_code
            print(f"Updated node: {name}")
    
    cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                (json.dumps(nodes, ensure_ascii=False), wf_id))
    conn.commit()
    print("SQLite saved!")

conn.close()

# Отправляем в TG
msg = f"🔍 Node9 code:\n\n{node9_code[:800]}\n\nTokens: {tokens}"
tg(msg)
if GH_PAT and GH_PAT not in node9_code:
    tg(f"✅ Token replaced in node9! New PAT injected.")
elif GH_PAT in node9_code:
    tg(f"ℹ️ Node9 already has correct PAT. Issue is elsewhere.")
PYEOF
