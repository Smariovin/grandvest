#!/usr/bin/env python3
"""
Проверка балансов всех сервисов проекта Grandvest
- OpenRouter (OR ключ)
- fal.ai
- GitHub Actions (минуты)
"""
import urllib.request, urllib.error, urllib.parse, json, os, re, sqlite3

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
GH_TOKEN = os.environ.get('GH_TOKEN', '')

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': CHAT, 'text': m[:4000],
        'parse_mode': 'HTML', 'disable_web_page_preview': True
    }).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e: print(f'TG error: {e}')

# Читаем ключи из SQLite
DB = '/opt/n8n/n8n_data/database.sqlite'
OR_KEY = ''
FAL_KEY = ''
try:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT nodes FROM workflow_entity")
    for (nodes_raw,) in cur.fetchall():
        if not OR_KEY:
            keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
            if keys: OR_KEY = keys[0]
        if not FAL_KEY:
            keys = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{30,}', nodes_raw)
            if keys: FAL_KEY = keys[0]
    conn.close()
except Exception as e:
    print(f'DB error: {e}')

print(f'OR key: {OR_KEY[:20]}...')
print(f'FAL key: {FAL_KEY[:20]}...')
print(f'GH token: {GH_TOKEN[:15]}...')

balances = []

# ─── 1. OpenRouter баланс ───
print('\n=== OpenRouter ===')
try:
    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/credits',
        headers={
            'Authorization': f'Bearer {OR_KEY}',
            'Content-Type': 'application/json'
        }
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
        print(f'Response: {d}')
        # Поля: credits, total_credits, usage
        total = d.get('total_credits', d.get('credits', 0))
        used = d.get('usage', 0)
        remaining = d.get('remaining', total - used if used else total)
        
        if isinstance(remaining, (int, float)):
            icon = '🟢' if remaining > 5 else '🟡' if remaining > 1 else '🔴'
            balances.append(f'{icon} <b>OpenRouter</b>\n'
                          f'   Остаток: ${remaining:.2f}\n'
                          f'   Использовано: ${used:.2f}')
        else:
            balances.append(f'🔵 <b>OpenRouter</b>: {d}')
except Exception as e:
    print(f'OR error: {e}')
    # Пробуем альтернативный endpoint
    try:
        req2 = urllib.request.Request(
            'https://openrouter.ai/api/v1/auth/key',
            headers={'Authorization': f'Bearer {OR_KEY}'}
        )
        with urllib.request.urlopen(req2, timeout=15) as r2:
            d2 = json.loads(r2.read().decode())
            print(f'Auth response: {d2}')
            data2 = d2.get('data', d2)
            limit = data2.get('limit', 'нет лимита')
            usage = data2.get('usage', 0)
            limit_remaining = data2.get('limit_remaining', None)
            
            if limit_remaining is not None:
                icon = '🟢' if limit_remaining > 5 else '🟡' if limit_remaining > 1 else '🔴'
                balances.append(f'{icon} <b>OpenRouter</b>\n'
                              f'   Лимит: ${limit}\n'
                              f'   Использовано: ${usage:.4f}\n'
                              f'   Остаток: ${limit_remaining:.4f}')
            else:
                balances.append(f'🔵 <b>OpenRouter</b>: лимит={limit}, использовано=${usage:.4f}')
    except Exception as e2:
        print(f'OR auth error: {e2}')
        balances.append(f'⚠️ <b>OpenRouter</b>: не удалось проверить\n   ({e2})')

# ─── 2. fal.ai баланс ───
print('\n=== fal.ai ===')
try:
    req = urllib.request.Request(
        'https://fal.run/fal-ai/credits',
        headers={
            'Authorization': f'Key {FAL_KEY}',
            'Content-Type': 'application/json'
        }
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
        print(f'fal response: {d}')
        credits = d.get('credits', d.get('balance', 0))
        icon = '🟢' if credits > 1 else '🟡' if credits > 0.1 else '🔴'
        balances.append(f'{icon} <b>fal.ai</b>\n   Кредиты: ${credits:.4f}')
except Exception as e:
    print(f'fal error: {e}')
    # Пробуем другой endpoint
    try:
        req2 = urllib.request.Request(
            'https://fal.run/fal-ai/billing',
            headers={'Authorization': f'Key {FAL_KEY}'}
        )
        with urllib.request.urlopen(req2, timeout=15) as r2:
            d2 = json.loads(r2.read().decode())
            print(f'fal billing: {d2}')
            balances.append(f'🔵 <b>fal.ai</b>: {str(d2)[:100]}')
    except Exception as e2:
        balances.append(f'⚠️ <b>fal.ai</b>: не удалось проверить\n   (проверь вручную: fal.ai/dashboard)')

# ─── 3. GitHub Actions минуты ───
print('\n=== GitHub Actions ===')
try:
    req = urllib.request.Request(
        'https://api.github.com/repos/Smariovin/grandvest/actions/billing/minutes',
        headers={
            'Authorization': f'token {GH_TOKEN}',
            'Accept': 'application/vnd.github+json'
        }
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
        print(f'GH minutes: {d}')
        used = d.get('total_minutes_used', 0)
        paid = d.get('total_paid_minutes_used', 0)
        included = d.get('included_minutes', 2000)
        remaining = included - used
        
        icon = '🟢' if remaining > 500 else '🟡' if remaining > 100 else '🔴'
        balances.append(f'{icon} <b>GitHub Actions</b>\n'
                       f'   Использовано: {used}/{included} мин\n'
                       f'   Остаток: {remaining} мин\n'
                       f'   Платных: {paid} мин')
except Exception as e:
    print(f'GH error: {e}')
    balances.append(f'⚠️ <b>GitHub Actions</b>: не удалось проверить\n   ({e})')

# ─── 4. Timeweb / VPS - пинг ───
print('\n=== VPS ===')
try:
    req = urllib.request.Request('http://85.239.61.157:5678/healthz', method='GET')
    urllib.request.urlopen(req, timeout=5)
    balances.append('🟢 <b>VPS Timeweb</b> (85.239.61.157)\n   n8n: работает ✅')
except Exception as e:
    balances.append(f'🔴 <b>VPS Timeweb</b> (85.239.61.157)\n   n8n: недоступен ❌')

# ─── Итоговый отчёт ───
from datetime import datetime, timezone, timedelta
msk = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%d.%m.%Y %H:%M')

report = [
    f'💰 <b>Баланс сервисов Grandvest</b>',
    f'🕐 {msk} МСК', ''
]
report.extend(balances)
report.append('')
report.append('📊 <i>Отчёт формируется автоматически</i>')

msg = '\n'.join(report)
print('\n' + msg)
tg(msg)
