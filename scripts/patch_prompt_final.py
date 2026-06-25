#!/usr/bin/env python3
"""
Точечный патч jsonBody в HTTP Request — генерация поста
Меняем: max_tokens 800→2048, промпт короткий→развёрнутый
jsonBody хранится как строка (str), не dict
"""
import sqlite3, json, subprocess, re, urllib.request, urllib.parse

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e:
        print(f'TG error: {e}')

NEW_SYSTEM = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые, аналитические посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА (строго соблюдай):\n\n"
    "🏢 [ЗАГОЛОВОК — суть новости 8-12 слов]\n\n"
    "По данным аналитиков, [факт с цифрами]. [Развитие мысли 2-3 предложения с конкретикой].\n\n"
    "[КОНТЕКСТ — 3-4 предложения]: причины, конкретные районы Москвы, ставки аренды руб/м², сравнение с прошлым периодом.\n\n"
    "[ВЛИЯНИЕ — 2-3 предложения]: что это значит для арендаторов, инвесторов, собственников?\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения от лица агентства — профессиональная оценка и польза для клиента]\n\n"
    "💡 Практический совет: [2 конкретных предложения — что сделать прямо сейчас]\n\n"
    "👉 За подбором объекта — @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: длина 900-1200 символов. Только конкретика и цифры. Никакой воды и общих фраз."
)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
nodes = json.loads(row[0])

patched = False
for n in nodes:
    name = n.get('name', '')
    if name != 'HTTP Request — генерация поста':
        continue

    params = n.get('parameters', {})
    json_body_str = params.get('jsonBody', '')

    print(f"Found node: {name!r}")
    print(f"jsonBody type: {type(json_body_str).__name__}")
    print(f"jsonBody (first 200): {json_body_str[:200]}")

    # jsonBody — строка, парсим
    try:
        body = json.loads(json_body_str)
    except Exception as e:
        print(f"Parse error: {e}")
        break

    old_mt = body.get('max_tokens', '?')
    body['max_tokens'] = 2048

    # Меняем системный промпт
    for msg in body.get('messages', []):
        if msg.get('role') == 'system':
            old_content = msg.get('content', '')
            print(f"Old system prompt ({len(old_content)} chars): {old_content[:100]!r}")
            msg['content'] = NEW_SYSTEM
            print(f"New system prompt ({len(NEW_SYSTEM)} chars)")

    # Сохраняем обратно как строку
    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
    n['parameters'] = params
    patched = True

    print(f"max_tokens: {old_mt} → 2048")
    print("PATCHED!")

if patched:
    cur.execute(
        "UPDATE workflow_entity SET nodes = ? WHERE id = 'F24jvKiXJIs4wRiZ'",
        (json.dumps(nodes, ensure_ascii=False),)
    )
    conn.commit()
    print("DB saved!")
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=30)
    print("n8n restarted!")
    tg("✅ Промпт обновлён!\nmax_tokens: 800 → 2048\nДлина: 800 → 900-1200 символов\nn8n перезапущен. Тестирую...")
else:
    print("ERROR: node not found or not patched!")
    tg("❌ Патч не применился — узел не найден")

conn.close()
