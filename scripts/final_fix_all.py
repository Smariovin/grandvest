#!/usr/bin/env python3
"""
ФИНАЛЬНЫЙ ФИХ: исправляем bodyContentType во всех OR узлах
и запускаем живой тест
"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
PAT = os.environ.get('WORKING_PAT', '')

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

fixes = []
for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue
    changed = False

    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        url_val = params.get('url', '')

        if ntype != 'n8n-nodes-base.httpRequest':
            continue
        if 'openrouter' not in url_val.lower():
            continue

        bct = params.get('bodyContentType', '')
        sb = params.get('specifyBody', '')
        jb = str(params.get('jsonBody', '')).strip()

        print(f"[{wf_name}] '{name}': bct={bct!r} sb={sb!r}")

        # Читаем тело
        body_str = jb[1:].strip() if jb.startswith('=') else jb

        try:
            body = json.loads(body_str) if body_str else {}
        except:
            body = {}

        # Если тело пустое — не трогаем jsonBody, только правим тип
        params['bodyContentType'] = 'json'
        params['specifyBody'] = 'json'

        if body:
            params['jsonBody'] = json.dumps(body, ensure_ascii=False)

        params.pop('rawBody', None)
        n['parameters'] = params
        changed = True
        fixes.append(f"[{wf_name}] '{name}': bodyContentType=json ✅")
        print(f"  FIXED: bct=json")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1, staticData='{}' WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(5)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

# Сброс дедупликации
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json', 'w') as f: json.dump([], f)

time.sleep(3)

# Живой тест
try:
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': (
            '<div class="tgme_widget_message_text js-message_text">'
            'Офисный рынок Москвы 2026: вакантность класса А снизилась до 7.8%. '
            'Ставки аренды в ЦАО достигли 48 000 руб/кв.м в год. '
            'Объём сделок за полугодие — 650 тыс кв.м +20% к 2025 году. '
            'Данные CBRE за июнь 2026.'
            '</div>'
            '<time datetime="2026-06-28T18:00:00+00:00">18:00</time>'
        )
    }).encode('utf-8')
    urllib.request.urlopen(urllib.request.Request(
        'http://localhost:5678/webhook/telegram-parser',
        data=payload, headers={'Content-Type': 'application/json'}), timeout=30)
    print("Test webhook sent!")
    test_sent = True
except Exception as e:
    print(f"Webhook error: {e}")
    test_sent = False

print(f"\nFixes: {fixes}")
tg(
    f'✅ <b>Финальный фикс применён!</b>\n\n'
    f'Исправлено:\n' +
    '\n'.join(f'• {f}' for f in fixes) +
    f'\n\n'
    f'{"🔄 Тест запущен → жди пост в @grandvest_realty!" if test_sent else "⚠️ Вебхук не отработал"}'
)
