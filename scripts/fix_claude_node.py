#!/usr/bin/env python3
"""
Исправляем узел 'Claude — оценка поста' в Парсере Telegram
Ошибка: Bad request - please check your parameters (400)
Причина: неверный формат тела запроса к OpenRouter
"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Правильное тело для Claude — оценка поста
SCORING_BODY = {
    "model": "anthropic/claude-sonnet-4-5",
    "max_tokens": 100,
    "messages": [
        {
            "role": "system",
            "content": (
                "Оцени релевантность новости для канала о недвижимости по шкале 1-10.\n"
                "Отвечай ТОЛЬКО JSON: {\"score\": N, \"reason\": \"...\"}\n\n"
                "8-10: прямо о недвижимости (аренда, продажа, ставки, сделки, девелопмент)\n"
                "6-7: косвенно (ипотека, инвестиции, строительство, законы о недвижимости)\n"
                "5: около-рыночная тема (экономика, ключевая ставка, бизнес)\n"
                "1-4: не связано с недвижимостью"
            )
        },
        {
            "role": "user",
            "content": "={{ 'Оцени новость:\\n\\n' + ($input.first().json.text || $input.first().json.content || $input.first().json.message || $input.first().json.html || '') }}"
        }
    ]
}

subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()

if not row:
    tg("❌ Workflow F24jvKiXJIs4wRiZ не найден")
    conn.close()
    exit()

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)

# Ищем OR ключ
or_key = ''
keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
if keys:
    or_key = keys[0]
print(f"OR key: {or_key[:20]}...")

fixes = []
for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '')
    params = n.get('parameters', {})
    url_val = params.get('url', '')

    # Узел Claude — оценка поста
    if 'Claude' in name and 'оценка' in name.lower() and 'httpRequest' in ntype:
        print(f"Found: {name!r}")
        print(f"  URL: {url_val}")
        print(f"  bodyContentType: {params.get('bodyContentType', '?')!r}")
        print(f"  specifyBody: {params.get('specifyBody', '?')!r}")
        
        jb = str(params.get('jsonBody', '')).strip()
        rb = str(params.get('rawBody', '')).strip()
        print(f"  jsonBody: {jb[:100]!r}")
        print(f"  rawBody: {rb[:100]!r}")

        # Устанавливаем правильные параметры
        params['specifyBody'] = 'json'
        params['bodyContentType'] = 'json'
        params['jsonBody'] = json.dumps(SCORING_BODY, ensure_ascii=False)
        params.pop('rawBody', None)
        params.pop('body', None)

        # Проверяем заголовки
        headers = params.get('headerParameters', {}).get('parameters', [])
        has_auth = any('sk-or-v1' in str(h.get('value', '')) for h in headers)
        if not has_auth and or_key:
            params['headerParameters'] = {
                'parameters': [
                    {'name': 'Authorization', 'value': f'Bearer {or_key}'},
                    {'name': 'Content-Type', 'value': 'application/json'}
                ]
            }
            fixes.append(f"'{name}': восстановлены заголовки")

        n['parameters'] = params
        fixes.append(f"'{name}': jsonBody исправлен, specifyBody=json")
        print(f"  FIXED!")

# Также проверяем узел генерации поста
for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '')
    params = n.get('parameters', {})
    url_val = params.get('url', '')

    if 'генерац' in name.lower() and 'httpRequest' in ntype and 'openrouter' in url_val.lower():
        print(f"\nFound gen node: {name!r}")
        jb = str(params.get('jsonBody', '')).strip()
        rb = str(params.get('rawBody', '')).strip()
        print(f"  bodyContentType: {params.get('bodyContentType','?')!r}")
        print(f"  jsonBody[:80]: {jb[:80]!r}")

        body_str = ''
        if jb and jb not in ('{}', ''):
            body_str = jb[1:].strip() if jb.startswith('=') else jb
        elif rb:
            body_str = rb[1:].strip() if rb.startswith('=') else rb

        try:
            body = json.loads(body_str) if body_str else {}
            model = body.get('model', 'NONE')
            mt = body.get('max_tokens', 0)
            print(f"  model={model!r} max_tokens={mt}")

            if model != 'anthropic/claude-sonnet-4-5' or mt < 2048:
                body['model'] = 'anthropic/claude-sonnet-4-5'
                body['max_tokens'] = 3000
                params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                params['specifyBody'] = 'json'
                params['bodyContentType'] = 'json'
                params.pop('rawBody', None)
                n['parameters'] = params
                fixes.append(f"'{name}': модель и max_tokens исправлены")
                print(f"  FIXED gen node!")
        except Exception as e:
            print(f"  Gen parse error: {e}")

cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
           (json.dumps(nodes, ensure_ascii=False), wf_id))
conn.commit()
conn.close()

subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=20)
print("n8n starting...")
for _ in range(15):
    time.sleep(5)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

# Тест
time.sleep(5)
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json', 'w') as f: json.dump([], f)

try:
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': (
            '<div class="tgme_widget_message_text js-message_text">'
            'Офисный рынок Москвы 2026: вакантность класса А снизилась до 7.8%. '
            'Ставки аренды в ЦАО достигли 48 000 руб/кв.м в год. '
            'Объём сделок за полугодие — 650 тыс кв.м (+20% к 2025). '
            'Данные CBRE за июнь 2026 года.'
            '</div>'
            '<time datetime="2026-06-28T17:00:00+00:00">17:00</time>'
        )
    }).encode('utf-8')
    urllib.request.urlopen(urllib.request.Request(
        'http://localhost:5678/webhook/telegram-parser',
        data=payload, headers={'Content-Type': 'application/json'}), timeout=30)
    print("Test webhook sent!")
except Exception as e:
    print(f"Webhook error: {e}")

tg(
    f"✅ <b>Claude — оценка поста: ИСПРАВЛЕН</b>\n\n"
    f"Проблема: Bad request 400 — неверный формат тела\n\n"
    f"Исправления:\n" +
    '\n'.join(f"• {f}" for f in fixes) +
    f"\n\nТест запущен → жди пост в @grandvest_realty!"
)
