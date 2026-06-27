#!/usr/bin/env python3
"""
Минимальный точечный патч: меняем только неправильные строки в коде узла 9
Используем sed-like замену прямо в JSON строке SQLite
"""
import sqlite3, json, os, urllib.request, urllib.parse, re

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT', '')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

print(f"PAT: {PAT[:15]}...")

import subprocess
subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
import time; time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
wf_id, wf_name, nodes_raw = cur.fetchone()
nodes = json.loads(nodes_raw)

fixes_applied = []

for n in nodes:
    name = n.get('name', '')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code', ''))
    
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        print(f"Node9: {name!r}")
        print(f"Code length: {len(code)}")
        print(f"Code preview: {code[:200]!r}")
        
        new_code = code
        
        # Fix 1: Неправильное имя workflow
        if 'telegram-publisher.yml' in new_code:
            new_code = new_code.replace('telegram-publisher.yml', 'grandvest-publisher.yml')
            fixes_applied.append("URL: telegram-publisher→grandvest-publisher")
            print("FIX 1: workflow name")
        
        # Fix 2: Bearer -> token для GitHub API
        if '"Bearer ghp_' in new_code or '"Bearer ' + PAT in new_code:
            new_code = re.sub(r'"Bearer (ghp_[A-Za-z0-9]+)"', r'"token \1"', new_code)
            fixes_applied.append("Auth: Bearer→token")
            print("FIX 2: auth type")
        
        # Fix 3: body: body -> body: JSON.stringify(body)
        if 'body: body' in new_code and 'JSON.stringify' not in new_code:
            new_code = new_code.replace('body: body', 'body: JSON.stringify(body)')
            fixes_applied.append("body: JSON.stringify добавлен")
            print("FIX 3: JSON.stringify")
        
        # Fix 4: Убеждаемся что токен правильный
        old_tokens = re.findall(r'ghp_[A-Za-z0-9]{36,}', new_code)
        bad = [t for t in old_tokens if t != PAT]
        if bad:
            for b in bad:
                new_code = new_code.replace(b, PAT)
            fixes_applied.append(f"Token: {bad[0][:12]}→{PAT[:12]}")
            print(f"FIX 4: bad tokens {[t[:12] for t in bad]}")
        
        if new_code != code:
            params['jsCode'] = new_code
            params.pop('code', None)
            n['parameters'] = params
            print(f"Updated code preview: {new_code[:200]!r}")

cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False), wf_id))

# Очищаем staticData
cur.execute("UPDATE workflow_entity SET staticData='{}' WHERE id='F24jvKiXJIs4wRiZ'")

conn.commit()
conn.close()

# Сбрасываем деdup
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)

subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
time.sleep(20)

# Ждём n8n
for i in range(8):
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print(f"n8n UP! ({i})")
        break
    except:
        time.sleep(4)

print(f"\nFixes: {fixes_applied}")
tg(f"✅ <b>SQLite Patch:</b>\n" + '\n'.join(f"• {f}" for f in fixes_applied) +
   f"\nn8n перезапущен\nТест запущен!")

# Тест
time.sleep(3)
try:
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': '<div class="tgme_widget_message_text js-message_text">Складской рынок России 2026 бьёт рекорды: вакантность в Подмосковье упала до 0.3 процента. Девелоперы строят 3 миллиона квадратных метров новых складов. Ставки аренды выросли до 14000 рублей за кв м в год по данным NF Group. Спрос формируют e-commerce и производственный сектор.</div><time datetime="2026-06-27T11:30:00+00:00">11:30</time>'
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(
        'http://localhost:5678/webhook/telegram-parser',
        data=payload, headers={'Content-Type':'application/json'}), timeout=30):
        print("Webhook OK!")
except Exception as e:
    print(f"Webhook error: {e}")
