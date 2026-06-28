#!/bin/bash
curl -s -c /tmp/rss_str_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

curl -s -b /tmp/rss_str_ck.txt \
  'http://localhost:5678/rest/workflows/SIPnV2mqmgMqUkLb' | python3 << 'PYEOF'
import sys, json, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])

report = [f'<b>RSS Workflow структура ({len(nodes)} узлов):</b>\n']
for n in nodes:
    name = n.get('name', '?')
    ntype = n.get('type', '?').split('.')[-1]
    params = n.get('parameters', {})
    url = params.get('url', '')[:50]
    code = params.get('jsCode', params.get('code', ''))[:60]
    
    detail = url or code or ''
    report.append(f'• <b>{name}</b> [{ntype}] {detail}')

print('\n'.join(report))
tg('\n'.join(report))
PYEOF
