#!/usr/bin/env python3
"""
ФИНАЛЬНЫЙ ФИХ RSS:
- HTTP Request6: Body Type Raw -> JSON
- Модель: любая невалидная -> claude-sonnet-4-5
- max_tokens: -> 2048
- Сохраняем через n8n API (не SQLite) чтобы n8n подхватил мгновенно
"""
import subprocess, json, os, re, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Логин
subprocess.run(['curl','-s','-c','/tmp/rss_ck.txt','-X','POST',
    'http://localhost:5678/rest/login',
    '-H','Content-Type: application/json',
    '-d','{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'],
    capture_output=True, timeout=10)

# Получаем все workflows
r = subprocess.run(['curl','-s','-b','/tmp/rss_ck.txt',
    'http://localhost:5678/rest/workflows'],
    capture_output=True, text=True, timeout=15)
all_wfs = json.loads(r.stdout).get('data', [])
print(f"Workflows: {len(all_wfs)}")

PROMPT_SYSTEM = (
    "Ты - эксперт по рынку недвижимости России с 15-летним опытом. "
    "Пишешь посты для Telegram канала агентства Grandvest (Москва).\n\n"
    "Переписывай новость в формате экспертного поста, сохраняя суть оригинала.\n\n"
    "СТРУКТУРА:\n"
    "🏢 [ЗАГОЛОВОК — точно отражает суть новости, 8-12 слов]\n\n"
    "[ФАКТЫ: 4-5 предложений с цифрами и датами из новости]\n\n"
    "[КОНТЕКСТ: 3-4 предложения — связь с рынком недвижимости]\n\n"
    "[ВЛИЯНИЕ: 2-3 предложения для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения]\n\n"
    "💡 Практический совет: [2 предложения]\n\n"
    "👉 @Grandvest_bot\n\n"
    "ТРЕБОВАНИЯ: 1500-2000 символов. Только факты из новости."
)

fixes = []

for wf_info in all_wfs:
    wf_id = wf_info['id']
    wf_name = wf_info['name']

    # Получаем детали
    r = subprocess.run(['curl','-s','-b','/tmp/rss_ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'],
        capture_output=True, text=True, timeout=15)
    try:
        wf = json.loads(r.stdout).get('data', {})
    except:
        continue
    
    nodes = wf.get('nodes', [])
    changed = False
    or_key = ''

    # Ищем OR ключ
    for n in nodes:
        for h in n.get('parameters',{}).get('headerParameters',{}).get('parameters',[]):
            v = str(h.get('value',''))
            if 'sk-or-v1' in v:
                or_key = v.replace('Bearer ','').strip()

    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        url = params.get('url', '')

        if ntype != 'n8n-nodes-base.httpRequest':
            continue
        if 'openrouter' not in url.lower():
            continue

        print(f"\n[{wf_name}] Node: {name!r}")

        # Читаем текущее тело из всех возможных мест
        jb = str(params.get('jsonBody', '')).strip()
        rb = str(params.get('rawBody', params.get('body', ''))).strip()
        body_type = params.get('bodyContentType', params.get('rawContentType', ''))
        specify = params.get('specifyBody', '')

        print(f"  bodyContentType: {body_type!r}")
        print(f"  specifyBody: {specify!r}")
        print(f"  jsonBody: {jb[:80]!r}")
        print(f"  rawBody: {rb[:80]!r}")

        # Определяем откуда брать тело
        body_str = ''
        if jb and jb not in ('{}', '""', "''", ''):
            body_str = jb[1:].strip() if jb.startswith('=') else jb
        elif rb and rb not in ('{}', '""', "''", ''):
            body_str = rb[1:].strip() if rb.startswith('=') else rb

        # Определяем user content по типу workflow
        is_rss = 'RSS' in wf_name or 'новост' in wf_name.lower() or 'сбор' in wf_name.lower()
        if is_rss:
            user_content = "={{ 'Перепиши эту новость в формате экспертного поста:\\n\\nИсточник: ' + ($input.first().json.source || 'RSS') + '\\nСсылка: ' + ($input.first().json.link || '') + '\\n\\nЗаголовок: ' + ($input.first().json.title || '') + '\\n\\nТекст:\\n' + ($input.first().json.description || $input.first().json.content || $input.first().json.text || '') }}"
        else:
            user_content = "={{ 'Перепиши эту новость в формате экспертного поста:\\n\\nИсточник: ' + ($input.first().json.source || $input.first().json.channel || 'Telegram') + '\\n\\nТекст новости:\\n' + ($input.first().json.text || $input.first().json.content || $input.first().json.message || '') }}"

        try:
            body = json.loads(body_str) if body_str else {}
            model = body.get('model', 'NONE')
            mt = body.get('max_tokens', 0)
            print(f"  Parsed: model={model!r} max_tokens={mt}")

            # Обновляем
            body['model'] = 'anthropic/claude-sonnet-4-5'
            body['max_tokens'] = 3000
            
            # Обновляем messages
            msgs = body.get('messages', [])
            has_system = any(m.get('role') == 'system' for m in msgs)
            has_user = any(m.get('role') == 'user' for m in msgs)
            
            new_msgs = []
            if has_system:
                for m in msgs:
                    if m.get('role') == 'system':
                        m['content'] = PROMPT_SYSTEM
                    elif m.get('role') == 'user':
                        m['content'] = user_content
                    new_msgs.append(m)
            else:
                new_msgs = [
                    {'role': 'system', 'content': PROMPT_SYSTEM},
                    {'role': 'user', 'content': user_content}
                ]
            body['messages'] = new_msgs

        except (json.JSONDecodeError, Exception) as e:
            print(f"  Body parse error: {e} — rebuilding from scratch")
            body = {
                'model': 'anthropic/claude-sonnet-4-5',
                'max_tokens': 3000,
                'messages': [
                    {'role': 'system', 'content': PROMPT_SYSTEM},
                    {'role': 'user', 'content': user_content}
                ]
            }

        # Применяем — ВСЕГДА JSON body type
        params['specifyBody'] = 'json'
        params['bodyContentType'] = 'json'
        params['jsonBody'] = json.dumps(body, ensure_ascii=False)
        params.pop('rawBody', None)
        params.pop('body', None)
        n['parameters'] = params
        changed = True
        fixes.append(f"[{wf_name}] {name!r}: Raw→JSON, {model}→claude-sonnet-4-5, mt→3000")
        print(f"  ✅ FIXED!")

    if changed:
        # Сохраняем через n8n API
        payload = json.dumps(wf, ensure_ascii=False)
        r2 = subprocess.run(['curl','-s','-b','/tmp/rss_ck.txt','-X','PUT',
            f'http://localhost:5678/rest/workflows/{wf_id}',
            '-H','Content-Type: application/json',
            '-d', payload],
            capture_output=True, text=True, timeout=20)
        result = json.loads(r2.stdout)
        saved = len(result.get('data', result).get('nodes', []))
        if saved > 0:
            print(f"  Saved {wf_name}: {saved} nodes ✅")
            # Активируем
            subprocess.run(['curl','-s','-b','/tmp/rss_ck.txt','-X','POST',
                f'http://localhost:5678/rest/workflows/{wf_id}/activate',
                '-H','Content-Type: application/json','-d','{}'],
                capture_output=True, timeout=10)
        else:
            print(f"  Save FAILED: {r2.stdout[:200]}")

print(f"\n=== FIXES ===")
for f in fixes: print(f"  {f}")

if fixes:
    tg("✅ <b>RSS Final Fix:</b>\n" + '\n'.join(f"• {f}" for f in fixes) +
       "\n\nBody: Raw→JSON\nМодель: →claude-sonnet-4-5\nmax_tokens: →3000")
else:
    tg("⚠️ RSS: ничего не исправлено — OR узлы не найдены")
