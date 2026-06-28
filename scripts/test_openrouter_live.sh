#!/bin/bash
python3 << 'PYEOF'
import urllib.request, json, re, sqlite3, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Читаем OR ключ из SQLite
OR_KEY = ''
try:
    db = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
    cur = db.cursor()
    cur.execute("SELECT nodes FROM workflow_entity")
    for (nodes_raw,) in cur.fetchall():
        keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
        if keys: OR_KEY = keys[0]; break
    db.close()
except Exception as e:
    print(f'DB error: {e}')

print(f'OR key: {OR_KEY[:25]}...')

# 1. Проверяем баланс
balance_info = ''
try:
    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/auth/key',
        headers={'Authorization': f'Bearer {OR_KEY}'}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
        data_d = d.get('data', d)
        limit = data_d.get('limit', 'нет')
        usage = data_d.get('usage', 0)
        remaining = data_d.get('limit_remaining', None)
        is_free = data_d.get('is_free_tier', False)
        balance_info = (
            f'Лимит: ${limit}\n'
            f'Использовано: ${usage:.4f}\n'
            f'Остаток: ${remaining:.4f if remaining else "?"}\n'
            f'Free tier: {is_free}'
        )
        print(f'Balance: {balance_info}')
except Exception as e:
    balance_info = f'Ошибка: {e}'
    print(f'Balance error: {e}')

# 2. Реальный тест запроса
test_result = ''
try:
    test_body = {
        'model': 'anthropic/claude-sonnet-4-5',
        'max_tokens': 30,
        'messages': [
            {'role': 'user', 'content': 'Ответь одним словом: OK'}
        ]
    }
    req2 = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps(test_body).encode(),
        headers={
            'Authorization': f'Bearer {OR_KEY}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://grandvest.ru'
        }
    )
    with urllib.request.urlopen(req2, timeout=30) as r2:
        d2 = json.loads(r2.read().decode())
        content = d2.get('choices',[])[0].get('message',{}).get('content','?')
        test_result = f'✅ Запрос OK! Ответ: {content}'
        print(test_result)
except urllib.request.HTTPError as e:
    err = e.read().decode()
    test_result = f'❌ HTTP {e.code}: {err[:150]}'
    print(test_result)
except Exception as e:
    test_result = f'❌ Error: {e}'
    print(test_result)

tg(
    f'<b>🔍 OpenRouter диагностика с VPS:</b>\n\n'
    f'<b>Баланс:</b>\n{balance_info}\n\n'
    f'<b>Тест запроса:</b>\n{test_result}'
)
PYEOF
