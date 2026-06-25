#!/usr/bin/env python3
"""
Диагностика и восстановление узла генерации поста.
OR ключ берём из существующего кода в БД.
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

NEW_SYSTEM_PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь содержательные посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА:\n\n"
    "EMOJI [ЗАГОЛОВОК - суть новости 8-12 слов]\n\n"
    "По данным аналитиков, [факт с цифрами]. [Развитие мысли]. [Ещё деталь]. [Итог].\n\n"
    "[КОНТЕКСТ - 3-4 предложения]: причины, районы, ставки аренды, сравнение с прошлым.\n\n"
    "[ВЛИЯНИЕ - 2-3 предложения]: что значит для арендаторов и инвесторов?\n\n"
    "EMOJI Комментарий Грандвест: [2-3 предложения от лица агентства]\n\n"
    "EMOJI Практический совет: [2 конкретных предложения]\n\n"
    "За подбором объекта - @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов, только конкретика, никакой воды."
)

# Читаем workflow
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
nodes = json.loads(row[0])

report = []
report.append(f"Total nodes: {len(nodes)}")

# Показываем все узлы
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','').split('.')[-1]
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    url = params.get('url','')
    report.append(f"\n{name} [{ntype}]")
    if url: report.append(f"  url: {url[:60]}")
    if code: report.append(f"  code({len(code)}): {code[:60]!r}")

print('\n'.join(report))
tg('\n'.join(report[:50]))

# Ищем OR ключ в любом узле
or_key = ''
for n in nodes:
    params = n.get('parameters',{})
    all_text = json.dumps(params)
    keys = re.findall(r'sk-or-v1-[a-f0-9]+', all_text)
    if keys:
        or_key = keys[0]
        print(f"Found OR key in node {n.get('name','')!r}: {or_key[:20]}...")
        break

# Ищем и исправляем HTTP Request узел генерации
changed = False
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})

    # HTTP Request узел генерации
    if ntype == 'n8n-nodes-base.httpRequest':
        url_val = params.get('url','')
        body_val = params.get('jsonBody', params.get('body',''))
        body_str = json.dumps(body_val) if isinstance(body_val, dict) else str(body_val)
        
        if 'openrouter' in url_val.lower() or 'openrouter' in body_str.lower():
            print(f"\nFound HTTP Request + OpenRouter: {name!r}")
            print(f"Current max_tokens search: {'max_tokens' in body_str}")
            
            # Обновляем jsonBody
            try:
                body_data = json.loads(body_val) if isinstance(body_val, str) else body_val
                old_mt = body_data.get('max_tokens', '?')
                body_data['max_tokens'] = 2048
                
                # Обновляем системный промпт
                for msg in body_data.get('messages', []):
                    if msg.get('role') == 'system':
                        old_len = len(msg.get('content',''))
                        msg['content'] = NEW_SYSTEM_PROMPT
                        print(f"  System prompt: {old_len} -> {len(NEW_SYSTEM_PROMPT)} chars")
                
                params['jsonBody'] = json.dumps(body_data, ensure_ascii=False)
                n['parameters'] = params
                changed = True
                print(f"  max_tokens: {old_mt} -> 2048")
                print(f"  UPDATED!")
            except Exception as e:
                print(f"  Parse error: {e}")
                print(f"  Body type: {type(body_val)}")
                print(f"  Body: {body_str[:200]}")

    # Code узел с openrouter (мой патч сломал тип)
    elif ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode', params.get('code',''))
        if 'openrouter' in code.lower() and 'max_tokens' in code:
            print(f"\nFound CODE node with OpenRouter (BROKEN TYPE): {name!r}")
            print(f"This should be HTTP Request but became Code!")
            print(f"Code: {code[:300]}")
            
            # Это мой сломанный патч - нужно восстановить тип
            if or_key:
                n['type'] = 'n8n-nodes-base.httpRequest'
                n['typeVersion'] = 4.2
                
                # Парсим модель и другие параметры из кода
                model = 'anthropic/claude-sonnet-4-5'
                m = re.search(r"model['\"]?\s*:\s*['\"]([^'\"]+)['\"]", code)
                if m: model = m.group(1)
                
                n['parameters'] = {
                    "method": "POST",
                    "url": "https://openrouter.ai/api/v1/chat/completions",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {or_key}"},
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "HTTP-Referer", "value": "https://grandvest.ru"},
                            {"name": "X-Title", "value": "Grandvest"}
                        ]
                    },
                    "sendBody": True,
                    "bodyContentType": "json",
                    "specifyBody": "json",
                    "jsonBody": json.dumps({
                        "model": model,
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": NEW_SYSTEM_PROMPT},
                            {"role": "user", "content": "={{ 'Напиши экспертный пост о коммерческой недвижимости по этой новости:\\n\\n' + $input.first().json.text }}"}
                        ]
                    }, ensure_ascii=False)
                }
                changed = True
                print(f"  RESTORED as HTTP Request! model={model}")
            else:
                print("  ERROR: No OR key found to restore!")

if changed:
    cur.execute("UPDATE workflow_entity SET nodes = ? WHERE id = 'F24jvKiXJIs4wRiZ'",
                (json.dumps(nodes, ensure_ascii=False),))
    conn.commit()
    print("\nDB updated!")
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=30)
    print("n8n restarted!")
    tg("✅ Generation node fixed! max_tokens=2048, prompt expanded. Testing now...")
else:
    print("\nNothing changed - need deeper inspection")
    tg("⚠️ Nothing changed! Generation node not found with expected pattern.")

conn.close()
