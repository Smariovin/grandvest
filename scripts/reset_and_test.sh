#!/bin/bash
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/rt_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

python3 << PYEOF
import subprocess, json, os, re, urllib.request, urllib.parse

PAT = os.environ.get('WORKING_PAT','')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)
    except: pass

# Сбрасываем StaticData через n8n API
r = subprocess.run(['curl','-s','-b','/tmp/rt_ck.txt',
    'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ'],
    capture_output=True, text=True, timeout=15)
d = json.loads(r.stdout)
wf = d.get('data', d)

# Проверяем узлы
nodes = wf.get('nodes', [])
issues = []
for n in nodes:
    name = n.get('name','')
    code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
    ntype = n.get('type','')
    url = n.get('parameters',{}).get('url','')

    # Дедупликация
    if ('Дедупликац' in name or '2.' in name) and 'code' in ntype.lower():
        has_static = 'getWorkflowStaticData' in code
        has_fs = "require('fs')" in code
        has_dollar = '$input' in code
        syntax_ok = not ('.all()' in code and '$input' not in code)
        issues.append(f'Dedup: StaticData={has_static} fs={has_fs} $input={has_dollar} syntax={syntax_ok}')
        print(f'Dedup code: {code[:100]}')

    # Узел 9
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        bad_url = 'telegram-publisher' in code
        bad_auth = '"Bearer' in code
        has_stringify = 'JSON.stringify' in code
        tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        correct_token = all(t == PAT for t in tokens) if tokens else False
        issues.append(f'Node9: bad_url={bad_url} bad_auth={bad_auth} stringify={has_stringify} token_ok={correct_token}')
        if bad_url or bad_auth or not has_stringify or not correct_token:
            # Исправляем через PUT
            NODE9 = (
                f"const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
                f"const imgData = $('HTTP Request \u2014 fal.ai').first().json;\n"
                f"const imageUrl = imgData.images && imgData.images[0] ? imgData.images[0].url : '';\n"
                f"if (!postText || postText.length < 10) {{\n"
                f"  throw new Error('tg_post пустой');\n"
                f"}}\n"
                f"const resp = await this.helpers.httpRequest({{\n"
                f"  method: 'POST',\n"
                f"  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
                f"  headers: {{\n"
                f"    'Authorization': 'token {PAT}',\n"
                f"    'Accept': 'application/vnd.github+json',\n"
                f"    'Content-Type': 'application/json'\n"
                f"  }},\n"
                f"  body: JSON.stringify({{\n"
                f"    ref: 'main',\n"
                f"    inputs: {{ message: postText, image_url: imageUrl }}\n"
                f"  }})\n"
                f"}});\n"
                f"return [{{ json: {{ ok: true, len: postText.length }} }}];"
            )
            n['parameters']['jsCode'] = NODE9
            n['parameters'].pop('code', None)
            issues.append('Node9: FIXED')
            print('Node9 fixed!')

# Сбрасываем StaticData
wf['staticData'] = {}

# Сохраняем
r2 = subprocess.run(['curl','-s','-b','/tmp/rt_ck.txt','-X','PUT',
    'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ',
    '-H','Content-Type: application/json',
    '-d', json.dumps(wf, ensure_ascii=False)],
    capture_output=True, text=True, timeout=20)
result = json.loads(r2.stdout)
saved = len(result.get('data', result).get('nodes', []))
issues.append(f'Saved: {saved} nodes, staticData cleared')
print(f'Saved: {saved} nodes')

# Сброс файла дедупликации
import os as _os
_os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)
issues.append('Dedup file cleared')

tg('<b>🔍 Диагностика и исправление:</b>\n' + '\n'.join(f'• {i}' for i in issues))
print('Done!')
PYEOF

# Тест вебхука
sleep 3
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Центральный банк России снизил ключевую ставку до 20 процентов годовых на заседании 28 июня 2026 года. Решение повлияет на ставки по ипотеке и кредитам на коммерческую недвижимость. Эксперты ожидают снижения ставок аренды офисов класса А в Москве на 5-7 процентов.</div><time datetime=\"2026-06-28T08:30:00+00:00\">08:30</time>"}' \
  && echo "Webhook OK"

curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=🔄 StaticData сброшен, дедупликация очищена, тест запущен" > /dev/null
