#!/bin/bash
BOT_TOKEN="${BOT_TOKEN}"
CHANNEL="-1003971323034"

python3 << PYEOF
import urllib.request, json, os, urllib.parse

BOT_TOKEN = os.environ.get('BOT_TOKEN','')
CHANNEL = '-1003971323034'
ADMIN_CHAT = '5340000158'

def tg_admin(m):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': ADMIN_CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

print(f'Token: {BOT_TOKEN[:20]}...')

# 1. getMe
req = urllib.request.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/getMe')
with urllib.request.urlopen(req, timeout=10) as r:
    bot = json.loads(r.read().decode()).get('result', {})
    print(f'Bot: @{bot.get("username")} id={bot.get("id")}')
    bot_id = bot.get('id')

# 2. getChatMember
req2 = urllib.request.Request(
    f'https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id={CHANNEL}&user_id={bot_id}'
)
with urllib.request.urlopen(req2, timeout=10) as r2:
    d = json.loads(r2.read().decode())
    member = d.get('result', {})
    status = member.get('status', '?')
    print(f'Bot status in channel: {status}')
    print(f'Full member info: {json.dumps(member, indent=2, ensure_ascii=False)[:500]}')

    # Права
    is_admin = status in ('administrator', 'creator')
    can_post = member.get('can_post_messages', False)
    can_read = member.get('can_read_messages', False)
    is_anon = member.get('is_anonymous', False)

    report = (
        f'<b>🤖 Статус @Grandvest_bot в канале</b>\n\n'
        f'Статус: <b>{status}</b>\n'
        f'Администратор: {"✅" if is_admin else "❌"}\n'
        f'Может постить: {"✅" if can_post else "❌"}\n'
        f'Анонимный: {"да" if is_anon else "нет"}\n\n'
    )
    if is_admin:
        report += '✅ Бот является администратором — верификация через forwardMessage работает'
    else:
        report += ('⚠️ Бот НЕ является администратором.\n'
                   'Верификация через forwardMessage не будет работать.\n\n'
                   'Чтобы включить полную верификацию:\n'
                   '1. Открой канал @grandvest_realty\n'
                   '2. Настройки → Администраторы → Добавить\n'
                   '3. Найди @Grandvest_bot\n'
                   '4. Включи: Читать сообщения')
    print(report)
    tg_admin(report)
PYEOF
