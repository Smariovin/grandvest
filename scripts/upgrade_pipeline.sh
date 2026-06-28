#!/bin/bash
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
CHANNEL="-1003971323034"

curl -s -c /tmp/up_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

python3 << PYEOF
import subprocess, json, os, re, urllib.request, urllib.parse

PAT = os.environ.get('WORKING_PAT', '')
BOT = '8672691336:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHANNEL = '-1003971323034'

def tg_log(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': '5340000158', 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def n8n_get(wf_id):
    r = subprocess.run(['curl','-s','-b','/tmp/up_ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'],
        capture_output=True, text=True, timeout=15)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

def n8n_put(wf_id, wf):
    r = subprocess.run(['curl','-s','-b','/tmp/up_ck.txt','-X','PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

# Новый промпт — универсальный, без жёсткой привязки к теме
NEW_SYSTEM_PROMPT = """Ты - эксперт по рынку недвижимости России с 15-летним опытом. Пишешь посты для Telegram канала агентства недвижимости Grandvest (Москва).

Твоя задача: переписать новость в формате экспертного поста, сохраняя суть оригинала и добавляя профессиональный контекст.

СТРУКТУРА ПОСТА:
🏢 [ЗАГОЛОВОК — точно отражает суть новости, 8-12 слов]

[ФАКТЫ: 4-5 предложений с конкретными цифрами, датами, именами из оригинальной новости]

[КОНТЕКСТ: 3-4 предложения — как это связано с рынком недвижимости, что происходит в этом сегменте]

[ВЛИЯНИЕ: 2-3 предложения — что это значит для арендаторов, покупателей и инвесторов]

💼 Комментарий Грандвест: [2-3 предложения с позицией агентства]

💡 Практический совет: [2 конкретных предложения для читателей]

👉 За консультацией — @Grandvest_bot

ТРЕБОВАНИЯ:
- 1500-2000 символов (достаточно для полного раскрытия темы)
- Используй ТОЛЬКО факты из предоставленной новости
- Не придумывай данные
- Если новость не о недвижимости напрямую — покажи связь с рынком недвижимости
- Без markdown, только текст и эмодзи"""

# Новый user message — берёт текст из всех возможных полей
NEW_USER_MESSAGE = "={{ 'Перепиши эту новость в формате экспертного поста:\\n\\nИсточник: ' + ($input.first().json.source || $input.first().json.channel || 'Telegram') + '\\nВремя: ' + ($input.first().json.date || '') + '\\n\\nТекст новости:\\n' + ($input.first().json.text || $input.first().json.content || $input.first().json.message || $input.first().json.html || $input.first().json.description || 'нет текста') }}"

fixes = []

# Патчим Парсер Telegram
wf = n8n_get('F24jvKiXJIs4wRiZ')
nodes = wf.get('nodes', [])
changed = False

for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '')
    params = n.get('parameters', {})
    url = params.get('url', '')

    # HTTP Request — генерация поста
    if 'генерац' in name.lower() and 'httpRequest' in ntype:
        jb = str(params.get('jsonBody', '')).strip()
        clean = jb[1:].strip() if jb.startswith('=') else jb
        try:
            body = json.loads(clean)
            # Обновляем промпт и увеличиваем max_tokens
            body['max_tokens'] = 3000  # Больше токенов для полного текста
            for msg in body.get('messages', []):
                if msg.get('role') == 'system':
                    msg['content'] = NEW_SYSTEM_PROMPT
                if msg.get('role') == 'user':
                    msg['content'] = NEW_USER_MESSAGE
            params['jsonBody'] = json.dumps(body, ensure_ascii=False)
            n['parameters'] = params
            changed = True
            fixes.append("Генерация: промпт обновлён, max_tokens=3000, user msg исправлен")
            print("Fixed generation node!")
        except Exception as e:
            print(f"Generation fix error: {e}")

    # Узел 8 — Подготовка данных поста: добавляем source_url и source_name
    if '8.' in name or 'Подготовка' in name:
        code = params.get('jsCode', params.get('code', ''))
        if code and 'tg_post' in code:
            # Добавляем поля источника в подготовку
            new_code = code
            if 'source_url' not in code:
                # Добавляем source_url в возвращаемый объект
                new_code = new_code.replace(
                    'return [{',
                    '''// Добавляем данные источника
const sourceUrl = $input.first().json.url || $input.first().json.link || '';
const sourceName = $input.first().json.source || $input.first().json.channel || 'Telegram';
const sourceDate = $input.first().json.date || new Date().toISOString();
return [{'''
                )
                new_code = new_code.replace(
                    'tg_post:',
                    'source_url: sourceUrl,\n    source_name: sourceName,\n    source_date: sourceDate,\n    tg_post:'
                )
                if new_code != code:
                    params['jsCode'] = new_code
                    n['parameters'] = params
                    changed = True
                    fixes.append("Подготовка данных: добавлены source_url, source_name, source_date")
                    print("Fixed preparation node!")

    # Узел 9 — добавляем source в dispatch
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        code = params.get('jsCode', params.get('code', ''))
        if 'grandvest-publisher' in code and 'source_url' not in code:
            new_code = code.replace(
                "const postText = $('8. Подготовка данных поста').first().json.tg_post;",
                """const postData = $('8. Подготовка данных поста').first().json;
const postText = postData.tg_post;
const sourceUrl = postData.source_url || '';
const sourceName = postData.source_name || '';
const sourceDate = postData.source_date || '';"""
            )
            new_code = new_code.replace(
                "message: postText,",
                "message: postText,\n      source_url: sourceUrl,\n      source_name: sourceName,\n      source_date: sourceDate,"
            )
            if new_code != code:
                params['jsCode'] = new_code
                n['parameters'] = params
                changed = True
                fixes.append("Узел 9: передаёт source_url в publisher")
                print("Fixed node 9!")

if changed:
    result = n8n_put('F24jvKiXJIs4wRiZ', wf)
    saved = len(result.get('nodes', []))
    print(f"Saved Парсер Telegram: {saved} nodes")

tg_log("✅ <b>Pipeline upgrade applied:</b>\n" + '\n'.join(f"• {f}" for f in fixes))
print(f"Fixes: {fixes}")
PYEOF
