#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

RESULT=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
import sys, json

d = json.load(sys.stdin)
wf = d.get('data', d)
nodes = wf.get('nodes', [])
out = []

for n in nodes:
    name = n.get('name', '')
    if 'генерац' in name.lower() or name == 'HTTP Request — генерация поста':
        params = n.get('parameters', {})
        out.append(f'NODE: {name}')
        out.append(f'Keys: {list(params.keys())}')
        for k, v in params.items():
            vs = str(v)[:200]
            out.append(f'{k}={type(v).__name__}: {vs!r}')
        break

print('\n'.join(out))
")

# Отправляем в Telegram
MSG=$(echo "$RESULT" | head -30 | python3 -c "import sys; print(sys.stdin.read().replace('&','%26').replace('#','%23'))")
curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=🔍 Generation node params:
$RESULT" > /dev/null

echo "Sent to TG"
echo "$RESULT"
