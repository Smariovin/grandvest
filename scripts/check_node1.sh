#!/bin/bash
# Читаем код узла 1 (Парсинг HTML Telegram) чтобы понять что он ожидает на входе

curl -s -c /tmp/c1_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

curl -s -b /tmp/c1_ck.txt \
  'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000]}).encode(),
        method='POST'), timeout=10)

d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))

    # Узел 1 - Парсинг HTML
    if '1.' in name or 'Парсинг' in name:
        print(f'NODE 1: {name}')
        print(f'Code ({len(code)} chars):')
        print(code[:600])
        tg(f'<b>Узел 1: {name}</b>\nCode:\n<code>{code[:800]}</code>')
        break
" 2>&1
