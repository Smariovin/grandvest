#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

# Логин в n8n
curl -s -c /tmp/cr_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Читаем последние executions
curl -s -b /tmp/cr_ck.txt 'http://localhost:5678/rest/executions?limit=5' | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode(),
        method='POST'), timeout=10)

d = json.load(sys.stdin)
items = d.get('data', {})
if isinstance(items, dict): items = items.get('results', [])

report = ['<b>Последние executions:</b>']
for ex in items[:5]:
    wf = ex.get('workflowData', {}).get('name', ex.get('workflowId', '?'))
    status = ex.get('status', '?')
    t = str(ex.get('startedAt', '?'))[11:16]
    icon = '✅' if status == 'success' else '❌'
    report.append(f'{icon} {wf} [{t}] {status}')

tg('\n'.join(report))
print('\n'.join(report))
" 2>&1

# Сбрасываем дедупликацию
echo '[]' > /data/published_titles.json
echo "Dedup reset"

# Проверяем код узла 2 (дедупликация) и узла 9
curl -s -b /tmp/cr_ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
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

report = ['<b>Состояние узлов:</b>']
for n in nodes:
    name = n.get('name', '')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code', ''))
    
    if 'Дедупликац' in name or '2.' in name:
        has_dollar = '\$input' in code
        syntax_ok = '.all()' not in code.replace('\$input.all()', '')
        report.append(f'Dedup: \$input={has_dollar} syntax_ok={syntax_ok}')
        report.append(f'Code: {code[:80]!r}')
    
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        has_correct = 'grandvest-publisher' in code
        has_token = '\"token ' in code or \"'token \" in code
        has_stringify = 'JSON.stringify' in code
        report.append(f'Node9: correct_url={has_correct} token={has_token} stringify={has_stringify}')
        report.append(f'Code: {code[:80]!r}')

tg('\n'.join(report))
print('\n'.join(report))
" 2>&1

# Живой тест
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Офисный рынок Москвы 2026: вакантность класса А достигла 7.8 процента минимум за пять лет. Ставки аренды в ЦАО составляют 48000 рублей за квадратный метр в год по данным CBRE. Сделки с IT-компаниями обеспечили 34 процента объема аренды. Инвестиции в коммерческую недвижимость превысили 350 миллиардов рублей.</div><time datetime=\"2026-06-27T18:30:00+00:00\">18:30</time>"}' \
  && echo "Webhook OK"

curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=🔄 Тест запущен после reset дедупликации!" > /dev/null
