#!/bin/bash
GH_PAT="${GH_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

python3 << PYEOF
import sqlite3, json, subprocess, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
NEW_PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

if not NEW_PAT:
    tg('❌ GH_PAT env не передан!')
    exit(1)

print(f'New PAT: {NEW_PAT[:15]}...')

# Читаем все workflows и заменяем ВСЕ старые PAT токены
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

total_replacements = 0
for wf_id, wf_name, nodes_raw in rows:
    nodes_str = nodes_raw
    # Находим все ghp_ токены кроме нашего рабочего
    old_tokens = set(re.findall(r'ghp_[A-Za-z0-9]{36,}', nodes_str))
    old_tokens.discard(NEW_PAT)
    
    if old_tokens:
        print(f'WF {wf_name}: replacing {len(old_tokens)} old token(s): {[t[:15] for t in old_tokens]}')
        for old_tok in old_tokens:
            nodes_str = nodes_str.replace(old_tok, NEW_PAT)
            total_replacements += 1
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?", (nodes_str, wf_id))

cur.execute("UPDATE workflow_entity SET active=1")
conn.commit()
conn.close()

print(f'Total replacements: {total_replacements}')

if total_replacements > 0:
    # Перезапускаем n8n чтобы подхватил изменения
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=30)
    import time; time.sleep(20)
    print('n8n restarted!')

    # Сбрасываем дедупликацию
    with open('/data/published_titles.json', 'w') as f:
        json.dump([], f)
    print('Dedup reset!')

    # Тестовый вебхук
    time.sleep(5)
    try:
        payload = json.dumps({
            'channel': 'CRERussia',
            'html': '<div class="tgme_widget_message_text js-message_text">Офисный рынок Москвы 2026: вакантность класса А упала до 7.8%. Ставки в ЦАО 48000 руб/кв м в год по данным CBRE. IT-компании обеспечили 34% сделок.</div><time datetime="2026-06-26T10:00:00+00:00">10:00</time>'
        }).encode('utf-8')
        req = urllib.request.Request(
            'http://localhost:5678/webhook/telegram-parser',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=30)
        print('Test webhook sent!')
    except Exception as e:
        print(f'Webhook error: {e}')

    tg(
        f'✅ <b>Токен исправлен!</b>\n\n'
        f'Заменено токенов: {total_replacements}\n'
        f'Старый: ghp_Z6K33... (истёкший)\n'
        f'Новый: ghp_u753... (рабочий)\n\n'
        f'n8n перезапущен\n'
        f'Дедупликация сброшена\n'
        f'Тест запущен → жди пост в @grandvest_realty!'
    )
else:
    tg('ℹ️ Старых токенов не найдено — все уже заменены')
PYEOF
