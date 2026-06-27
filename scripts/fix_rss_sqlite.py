#!/usr/bin/env python3
"""
Исправляем RSS workflow:
1. HTTP Request6: модель gemini-flash-1.5 -> claude-sonnet-4-5
2. Body Type: Raw -> JSON  
3. max_tokens: -> 2048
"""
import sqlite3, json, subprocess, os, urllib.request, urllib.parse, re, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы. "
    "Напиши развёрнутый пост для Telegram канала Grandvest.\n\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "[ФАКТЫ 3-4 предл с цифрами]\n\n"
    "[КОНТЕКСТ: районы, ставки руб/кв.м.]\n\n"
    "[ВЛИЯНИЕ для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предл]\n\n"
    "💡 Практический совет: [2 предл]\n\n"
    "👉 @Grandvest_bot\n#коммерческаянедвижимость #москва\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика."
)

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
    # Ищем OR ключ
    or_key = ''
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: or_key = keys[0]
    
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        url = params.get('url', '')
        
        # Все HTTP Request узлы с OpenRouter
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            print(f"  [{wf_name}] '{name}'")
            
            # Пробуем все варианты хранения тела
            jb = str(params.get('jsonBody', '')).strip()
            rb = str(params.get('rawBody', params.get('body', ''))).strip()
            
            body_str = ''
            if jb and jb not in ('{}', '""', "''"):
                body_str = jb[1:].strip() if jb.startswith('=') else jb
            elif rb and rb not in ('{}', '""', "''"):
                body_str = rb[1:].strip() if rb.startswith('=') else rb
            
            print(f"    body_str preview: {body_str[:100]!r}")
            
            try:
                body = json.loads(body_str) if body_str else {}
                model = body.get('model', 'NONE')
                mt = body.get('max_tokens', 0)
                print(f"    model={model!r} max_tokens={mt}")
                
                need_fix = (model != 'anthropic/claude-sonnet-4-5' or mt < 2048)
                
                if need_fix:
                    body['model'] = 'anthropic/claude-sonnet-4-5'
                    body['max_tokens'] = 2048
                    
                    # Исправляем системный промпт если нужно
                    for msg in body.get('messages', []):
                        if msg.get('role') == 'system':
                            content = msg.get('content', '')
                            if len(content) < 50 or 'gemini' in content.lower():
                                msg['content'] = PROMPT
                    
                    # Сохраняем как JSON body (не Raw)
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    params['specifyBody'] = 'json'
                    params['bodyContentType'] = 'json'
                    params.pop('rawBody', None)
                    params.pop('body', None)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': {model}→claude-sonnet-4-5, mt={mt}→2048")
                    print(f"    FIXED!")
                    
            except json.JSONDecodeError as e:
                print(f"    JSONDecodeError: {e}")
                if or_key:
                    # Пересоздаём тело полностью
                    # Определяем user content по контексту
                    if 'RSS' in wf_name or 'новост' in wf_name.lower():
                        user_content = "={{ 'Напиши пост о коммерческой недвижимости по этой новости:\\n\\n' + ($input.first().json.title || $input.first().json.description || $input.first().json.text || 'нет данных') }}"
                    else:
                        user_content = "={{ 'Напиши пост по новости:\\n\\n' + ($input.first().json.text || '') }}"
                    
                    new_body = {
                        "model": "anthropic/claude-sonnet-4-5",
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": user_content}
                        ]
                    }
                    params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                    params['specifyBody'] = 'json'
                    params['bodyContentType'] = 'json'
                    params.pop('rawBody', None)
                    params.pop('body', None)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': REBUILT with claude-sonnet-4-5")
                    print(f"    REBUILT from scratch!")
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

print(f"\nFixes: {fixes}")

subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=20)
time.sleep(20)

for _ in range(8):
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except:
        time.sleep(4)

if fixes:
    tg("✅ <b>RSS SQLite Fix:</b>\n" + '\n'.join(f"• {f}" for f in fixes) +
       "\n\nМодель: gemini-flash → claude-sonnet-4-5\nBody: Raw → JSON")
else:
    # Показываем что нашли
    tg("ℹ️ Нет изменений — проверяю модели вручную...")
