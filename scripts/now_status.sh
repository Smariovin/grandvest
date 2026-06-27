#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
PAT="${WORKING_PAT}"

curl -s -c /tmp/ns_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# 1. Сбрасываем дедупликацию
echo '[]' > /data/published_titles.json

# 2. Проверяем ТОЧНЫЙ код узла 9 прямо сейчас
python3 -c "
import subprocess, json, re, os, urllib.request, urllib.parse

PAT = os.environ.get('WORKING_PAT','')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url=f'https://api.telegram.org/bot{BOT}/sendMessage'
    data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)

# Получаем Парсер Telegram
r = subprocess.run(['curl','-s','-b','/tmp/ns_ck.txt',
    'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ'],
    capture_output=True, text=True, timeout=15)
d = json.loads(r.stdout)
wf = d.get('data',d)
nodes = wf.get('nodes',[])

report = ['<b>Статус узлов Парсер Telegram:</b>']

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','').split('.')[-1]
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    url_val = params.get('url','')
    jb = params.get('jsonBody','')

    if ('Отправка' in name or '9.' in name) and 'code' in ntype.lower():
        tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        pub = 'grandvest-publisher' in code
        correct = all(t==PAT for t in tokens) if tokens else False
        report.append(f'<b>Узел 9:</b> pub={pub} token_ok={correct}')
        report.append(f'Tokens: {[t[:15] for t in tokens]}')
        report.append(f'Code[:100]: {code[:100]!r}')

    if 'фильтр' in name.lower():
        thresh = [l for l in code.split(chr(10)) if 'score >=' in l or 'score >' in l]
        report.append(f'<b>Фильтр:</b> {thresh}')

    if 'Дедупликац' in name:
        uses_static = 'getWorkflowStaticData' in code
        uses_fs = 'readFileSync' in code
        report.append(f'<b>Деdup:</b> static={uses_static} fs={uses_fs}')

    if 'httpRequest' in ntype and 'openrouter' in url_val.lower():
        jb_str = str(jb).strip()
        clean = jb_str[1:] if jb_str.startswith('=') else jb_str
        try:
            body = json.loads(clean)
            mt = body.get('max_tokens','?')
            report.append(f'<b>{name}:</b> max_tokens={mt}')
        except:
            report.append(f'<b>{name}:</b> jsonBody INVALID {jb_str[:50]!r}')

tg(chr(10).join(report))
print(chr(10).join(report))
" 2>&1

# 3. Тест вебхука
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Вакантность офисов класса А в Москве упала до 7.8 процента по данным CBRE. Ставки аренды в ЦАО 48000 рублей за кв м в год. IT-компании заняли 34 процента рынка. Инвестиции в коммерческую недвижимость России превысили 350 миллиардов рублей.</div><time datetime=\"2026-06-27T10:00:00+00:00\">10:00</time>"}' \
  && echo "Webhook OK"

sleep 90

# 4. Читаем результат
curl -s -b /tmp/ns_ck.txt 'http://localhost:5678/rest/executions?limit=2' | python3 -c "
import sys,json,urllib.request,urllib.parse
BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'
def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode(),
        method='POST'),timeout=10)

d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])

result=['<b>После теста:</b>']
for ex in items[:2]:
    wf=ex.get('workflowData',{}).get('name','?')
    status=ex.get('status','?')
    t=str(ex.get('startedAt','?'))[11:16]
    icon='✅' if status=='success' else '❌'
    result.append(f'{icon} {wf} [{t}] {status}')

tg(chr(10).join(result))
print(chr(10).join(result))
" 2>&1
