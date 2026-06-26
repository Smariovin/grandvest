#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "=== LIVE CHAIN TEST ==="

# Читаем OR ключ из БД
OR_KEY=$(python3 -c "
import sqlite3, json, re
conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()
cur.execute('SELECT nodes FROM workflow_entity')
for (nodes_raw,) in cur.fetchall():
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: print(keys[0]); break
conn.close()
")
echo "OR Key: ${OR_KEY:0:20}..."

# Тест 1: OpenRouter напрямую
echo ""
echo "=== TEST OpenRouter API ==="
OR_RESP=$(curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer ${OR_KEY}" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: https://grandvest.ru" \
  -d '{"model":"anthropic/claude-sonnet-4-5","max_tokens":50,"messages":[{"role":"user","content":"Say OK"}]}')
echo "OR Response: $OR_RESP"

OR_OK=$(echo "$OR_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content','ERROR'))" 2>/dev/null || echo "PARSE ERROR")
echo "OR Content: $OR_OK"

tg "🔍 <b>OpenRouter тест:</b>
OR key: ${OR_KEY:0:20}...
Response: $OR_OK"

# Тест 2: Смотрим последний execution в деталях
echo ""
echo "=== LAST EXECUTION DETAILS ==="
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Получаем execution с деталями
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=10' | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(msg):
    url=f'https://api.telegram.org/bot{BOT}/sendMessage'
    data=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)

d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])

print(f'Total executions: {len(items)}')
msg=['<b>Recent executions:</b>']
for ex in items[:5]:
    wf=ex.get('workflowData',{}).get('name',ex.get('workflowId','?'))
    status=ex.get('status','?')
    t=str(ex.get('startedAt','?'))[11:16]
    mode=ex.get('mode','?')
    icon='✅' if status=='success' else '❌'
    msg.append(f'{icon} {wf} [{t}] mode={mode}')

tg('\n'.join(msg))
" 2>&1

# Тест 3: Отправляем вебхук и сразу проверяем execution
echo ""
echo "=== SEND WEBHOOK ==="
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"officenewsdaily","html":"<div class=\"tgme_widget_message_text js-message_text\">Новый деловой квартал в Москве привлечет инвесторов объем сделок аренды офисов вырос на 20 процентов в первом квартале 2026 года по данным JLL.</div><time datetime=\"2026-06-26T12:45:00+00:00\">12:45</time>"}' &
WPID=$!

sleep 45

# Читаем последний execution
curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=3' | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(msg):
    url=f'https://api.telegram.org/bot{BOT}/sendMessage'
    data=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)

d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])

for ex in items[:1]:
    wf=ex.get('workflowData',{}).get('name','?')
    status=ex.get('status','?')
    data_raw=json.dumps(ex.get('data',{}))
    
    # Парсим runData из data
    try:
        data=ex.get('data',{})
        rd=data.get('resultData',{}).get('runData',{})
        lines=[f'<b>{wf}: {status}</b>']
        for node_name, runs in rd.items():
            for r in (runs or []):
                es=r.get('executionStatus','?')
                err=r.get('error')
                out=r.get('data',{}).get('main',[[]])
                cnt=len(out[0]) if out and out[0] else 0
                icon='✅' if es=='success' else '❌' if err else '⚠️'
                line=f'{icon} {node_name}: {es} out={cnt}'
                if err:
                    line+=f' ERR:{err.get(\"message\",\"?\")[:60]}'
                lines.append(line)
        tg('\n'.join(lines))
    except Exception as e:
        tg(f'Parse error: {e}\nStatus: {status}')
" 2>&1

echo "DONE"
