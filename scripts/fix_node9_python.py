#!/usr/bin/env python3
"""
ФИНАЛЬНЫЙ ФИХ узла 9:
Проблемы из скриншота:
1. URL: telegram-publisher.yml -> grandvest-publisher.yml
2. Authorization: "Bearer ..." -> "token ..."  
3. body: body -> body: JSON.stringify(body)
"""
import subprocess, json, os, urllib.request, urllib.parse

PAT = os.environ.get('WORKING_PAT', '')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

print(f"PAT: {PAT[:15]}...")

# Логин
subprocess.run(['curl','-s','-c','/tmp/py_ck.txt','-X','POST',
    'http://localhost:5678/rest/login',
    '-H','Content-Type: application/json',
    '-d','{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'],
    capture_output=True, timeout=10)

# Получаем workflow
r = subprocess.run(['curl','-s','-b','/tmp/py_ck.txt',
    'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ'],
    capture_output=True, text=True, timeout=15)

d = json.loads(r.stdout)
wf = d.get('data', d)
nodes = wf.get('nodes', [])
print(f"Nodes: {len(nodes)}")

# Правильный код - ТОЧНО как должен выглядеть
CORRECT_CODE = (
    'const postText = $("8. Подготовка данных поста").first().json.tg_post;\n'
    'const imgData = $("HTTP Request \u2014 fal.ai").first().json;\n'
    'const imageUrl = imgData.images && imgData.images[0] ? imgData.images[0].url : "";\n'
    '\n'
    'if (!postText || postText.length < 10) {\n'
    '  throw new Error("tg_post пустой: " + JSON.stringify(postText));\n'
    '}\n'
    '\n'
    'const resp = await this.helpers.httpRequest({\n'
    '  method: "POST",\n'
    '  url: "https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches",\n'
    '  headers: {\n'
    '    "Authorization": "token ' + PAT + '",\n'
    '    "Accept": "application/vnd.github+json",\n'
    '    "Content-Type": "application/json"\n'
    '  },\n'
    '  body: JSON.stringify({\n'
    '    ref: "main",\n'
    '    inputs: {\n'
    '      message: postText,\n'
    '      image_url: imageUrl\n'
    '    }\n'
    '  })\n'
    '});\n'
    '\n'
    'return [{ json: { ok: true, len: postText.length } }];'
)

changed = False
for n in nodes:
    name = n.get('name', '')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code', ''))
    
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        print(f"\nFound Node9: {name!r}")
        print(f"Current URL in code: telegram-publisher={('telegram-publisher' in code)} grandvest-publisher={('grandvest-publisher' in code)}")
        print(f"Current auth: Bearer={('Bearer' in code)} token={('token ' in code)}")
        print(f"Current body: stringify={('JSON.stringify' in code)}")
        
        n['parameters']['jsCode'] = CORRECT_CODE
        n['parameters'].pop('code', None)
        changed = True
        print(f"FIXED! New code:")
        print(CORRECT_CODE[:300])

if not changed:
    print("Node9 not found! Listing all nodes:")
    for n in nodes:
        print(f"  {n.get('name','?')!r} type={n.get('type','?').split('.')[-1]}")
    tg("❌ Node9 не найден!")
    exit(1)

# Сохраняем через n8n API
payload = json.dumps(wf, ensure_ascii=False)
r2 = subprocess.run(
    ['curl','-s','-b','/tmp/py_ck.txt','-X','PUT',
     'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ',
     '-H','Content-Type: application/json',
     '-d', payload],
    capture_output=True, text=True, timeout=20
)

result = json.loads(r2.stdout)
saved = len(result.get('data', result).get('nodes', []))
print(f"\nSaved! {saved} nodes")

if saved > 0:
    tg(f"✅ <b>Node9 ФИНАЛЬНО исправлен:</b>\n"
       f"• URL: telegram-publisher → grandvest-publisher\n"
       f"• Auth: Bearer → token\n"
       f"• body: JSON.stringify добавлен\n\n"
       f"PAT: {PAT[:12]}...\n"
       f"Тест запущен!")
    
    # Сбрасываем деdup
    import os
    with open('/data/published_titles.json','w') as f:
        json.dump([], f)
    
    # Тест
    import time
    time.sleep(3)
    
    test_payload = json.dumps({
        'channel': 'CRERussia',
        'html': '<div class="tgme_widget_message_text js-message_text">Офисный рынок Москвы 2026 показал рекордный рост: вакантность класса А снизилась до 7.8 процента по данным CBRE. Ставки аренды в ЦАО составляют 48000 рублей за квадратный метр в год. Объем сделок за полугодие превысил 650 тысяч квадратных метров.</div><time datetime="2026-06-27T11:30:00+00:00">11:30</time>'
    }).encode()
    
    req = urllib.request.Request(
        'http://localhost:5678/webhook/telegram-parser',
        data=test_payload,
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Webhook: OK")
    except Exception as e:
        print(f"Webhook error: {e}")
else:
    tg(f"❌ Save failed: {str(result)[:100]}")
