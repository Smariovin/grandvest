#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Смотрим последний execution
LAST=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=1')

echo "$LAST" | python3 -c "
import sys,json,urllib.request,urllib.parse
BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'
def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000]}).encode(),
        method='POST'),timeout=10)

d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
if not items:
    tg('No executions found')
    exit()

ex=items[0]
wf=ex.get('workflowData',{}).get('name','?')
status=ex.get('status','?')
t=str(ex.get('startedAt','?'))[11:16]
eid=ex.get('id','?')
tg(f'Last exec: {wf}\nStatus: {status}\nTime: {t}\nID: {eid}')
print(f'{status} {wf} {t} id={eid}')
"

# Отправляем новый тест с реальной новостью
echo '[]' > /data/published_titles.json

curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Инвесторы вложили 85 миллиардов рублей в коммерческую недвижимость Москвы за первое полугодие 2026 года. Наибольший интерес представляют офисы класса А в деловых районах. По данным CBRE доходность составляет от 9 до 12 процентов годовых. Основные покупатели — российские институциональные инвесторы и частные лица с капиталом.</div><time datetime=\"2026-06-26T20:00:00+00:00\">20:00</time>"}' \
  && echo "Webhook sent"

sleep 60

# Проверяем что получилось
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=1' | python3 -c "
import sys,json,urllib.request,urllib.parse
BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'
def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000]}).encode(),
        method='POST'),timeout=10)

d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
if not items: tg('No execs'); exit()

ex=items[0]
wf=ex.get('workflowData',{}).get('name','?')
status=ex.get('status','?')
t=str(ex.get('startedAt','?'))[11:16]

icon='✅' if status=='success' else '❌'
tg(f'{icon} After fix test:\nWF: {wf}\nStatus: {status}\nTime: {t}')
print(f'{status} {wf} {t}')
"
