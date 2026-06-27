#!/bin/bash
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

# Логин
curl -s -c /tmp/fn_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Получаем workflow
WF_JSON=$(curl -s -b /tmp/fn_ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ')

python3 << PYEOF
import json, subprocess, os, urllib.request, urllib.parse

PAT = os.environ.get('WORKING_PAT', '')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Правильный код узла 9
# ОШИБКИ были:
# 1. telegram-publisher.yml -> grandvest-publisher.yml  
# 2. "Bearer ghp_..." -> "token ghp_..."
# 3. images[0].url -> images?.[0]?.url (защита от null)
# 4. body передавался как объект, нужен JSON.stringify
CORRECT_CODE = f'''const postText = $("8. Подготовка данных поста").first().json.tg_post;
const imgData = $("HTTP Request — fal.ai").first().json;
const imageUrl = imgData.images && imgData.images[0] ? imgData.images[0].url : "";

if (!postText || postText.length < 10) {{
  throw new Error("tg_post пустой: " + JSON.stringify(postText));
}}

const resp = await this.helpers.httpRequest({{
  method: "POST",
  url: "https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches",
  headers: {{
    "Authorization": "token {PAT}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json"
  }},
  body: JSON.stringify({{
    ref: "main",
    inputs: {{
      message: postText,
      image_url: imageUrl
    }}
  }})
}});

return [{{ json: {{ ok: true, len: postText.length }} }}];'''

wf = json.loads('''$WF_JSON'''.replace("'", "\\'"))
wf = wf.get('data', wf)
nodes = wf.get('nodes', [])

changed = False
for n in nodes:
    name = n.get('name', '')
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        old_code = n.get('parameters', {}).get('jsCode', '')
        print(f"Node9: {name}")
        print(f"Old URL: {'telegram-publisher' in old_code}")
        print(f"Old Bearer: {'Bearer' in old_code}")
        
        n['parameters']['jsCode'] = CORRECT_CODE
        n['parameters'].pop('code', None)
        changed = True
        print(f"FIXED!")
        print(f"New code preview: {CORRECT_CODE[:100]}")

if changed:
    payload = json.dumps(wf, ensure_ascii=False)
    r = subprocess.run(
        ['curl', '-s', '-b', '/tmp/fn_ck.txt', '-X', 'PUT',
         'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ',
         '-H', 'Content-Type: application/json',
         '-d', payload],
        capture_output=True, text=True, timeout=20
    )
    result = json.loads(r.stdout)
    saved = len(result.get('data', result).get('nodes', []))
    print(f"Saved! {saved} nodes")
    tg(f"✅ <b>Node9 исправлен!</b>\n\n"
       f"• telegram-publisher.yml → grandvest-publisher.yml\n"
       f"• Bearer → token\n"
       f"• body: JSON.stringify добавлен\n"
       f"• imageUrl: null-safe\n\n"
       f"Запускаю тест...")
else:
    print("Node9 not found!")
    tg("❌ Node9 not found")
PYEOF

# Сбрасываем деdup и тестируем
echo '[]' > /data/published_titles.json
sleep 3

curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Офисный рынок Москвы 2026: вакантность класса А упала до 7.8 процента. Ставки в ЦАО выросли до 48000 рублей за кв м в год. IT-компании заняли 34 процента от объема сделок аренды по данным CBRE. Инвестиции в коммерческую недвижимость превысили 350 миллиардов рублей за полугодие.</div><time datetime=\"2026-06-27T11:00:00+00:00\">11:00</time>"}' \
  && echo "Webhook OK"
