#!/bin/bash
GH_PAT="${GH_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

python3 << PYEOF
import sqlite3, json, subprocess, urllib.request, urllib.parse, os, re, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
NEW_PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

print(f"NEW_PAT: {NEW_PAT[:15]}...")

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развернутые посты для Telegram канала Grandvest.\n\n"
    "СТРУКТУРА:\n🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "[ФАКТЫ 3-4 предл с цифрами и источниками]\n\n"
    "[КОНТЕКСТ 3-4 предл: районы Москвы, ставки руб/кв м, сравнение]\n\n"
    "[ВЛИЯНИЕ 2-3 предл: для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предл]\n\n"
    "💡 Практический совет: [2 предл]\n\n"
    "👉 За подбором - @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика. Никакой воды."
)

NODE9_CODE = f"""// Отправка через GitHub Actions
const postText = $('8. Подготовка данных поста').first().json.tg_post;
const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';
if (!postText || postText.length < 10) {{
  throw new Error('tg_post пустой: ' + JSON.stringify(postText));
}}
console.log('Sending post:', postText.length, 'chars');
const r = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {{
    'Authorization': 'token {NEW_PAT}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github+json'
  }},
  body: JSON.stringify({{ref: 'main', inputs: {{message: postText, image_url: imageUrl}}}})
}});
console.log('GitHub dispatch OK');
return [{{json: {{ok: true, len: postText.length}}}}];"""

# Останавливаем n8n для чистой записи в SQLite
print("Stopping n8n...")
subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=30)
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
    all_text = nodes_raw
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', all_text)
    if keys: or_key = keys[0]
    
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        url = params.get('url', '')
        
        # === УЗЕЛ 9: принудительная замена всего кода ===
        is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is_node9:
            old_tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
            print(f"Node9 '{name}': tokens in code: {old_tokens}")
            # Перезаписываем весь код целиком
            n['parameters']['jsCode'] = NODE9_CODE
            n['parameters'].pop('code', None)
            changed = True
            fixes.append(f"[{wf_name}] Node9 перезаписан с PAT {NEW_PAT[:12]}...")
            print(f"  Node9 OVERWRITTEN!")
        
        # === OpenRouter узлы: исправляем jsonBody ===
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            jb = str(params.get('jsonBody', '')).strip()
            clean = jb[1:] if jb.startswith('=') else jb
            
            try:
                body = json.loads(clean)
                mt = body.get('max_tokens', 0)
                sys_ok = any('ТРЕБОВАНИЯ' in str(m.get('content',''))
                             for m in body.get('messages',[]) if m.get('role')=='system')
                
                if mt < 2048 or not sys_ok:
                    body['max_tokens'] = 2048
                    for m in body.get('messages',[]):
                        if m.get('role') == 'system':
                            m['content'] = PROMPT
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': max_tokens→2048")
                    print(f"  OR node '{name}' fixed!")
            except Exception as e:
                print(f"  OR node '{name}' parse error: {e}")
                if or_key:
                    # Пересоздаём
                    new_body = {
                        "model": "anthropic/claude-sonnet-4-5",
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": "={{ 'Напиши пост о коммерческой недвижимости по новости:\\n\\n' + ($input.first().json.text || $input.first().json.title || $input.first().json.description || '') }}"}
                        ]
                    }
                    params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                    params['specifyBody'] = 'json'
                    params['bodyContentType'] = 'json'
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': rebuilt")
                    print(f"  OR node '{name}' rebuilt!")
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))
        print(f"Saved: {wf_name}")

conn.commit()
conn.close()

print(f"\nFixes: {fixes}")

# Запускаем n8n
print("\nStarting n8n...")
subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=30)
time.sleep(25)

# Проверяем что n8n запустился
for i in range(5):
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except:
        print(f"Waiting... ({i+1}/5)")
        time.sleep(5)

# Сбрасываем дедупликацию
with open('/data/published_titles.json', 'w') as f:
    json.dump([], f)
print("Dedup reset!")

# Тест Парсера Telegram
time.sleep(5)
try:
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': '<div class="tgme_widget_message_text js-message_text">Офисная недвижимость Москвы 2026: вакантность класса А снизилась до 7.8%, ставки в ЦАО достигли 48000 руб/кв м/год по данным CBRE. IT-сектор обеспечил 34% от объема сделок аренды.</div><time datetime="2026-06-26T10:00:00+00:00">10:00</time>'
    }).encode()
    urllib.request.urlopen(
        urllib.request.Request('http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type': 'application/json'}), timeout=30)
    print("Parser webhook sent!")
except Exception as e:
    print(f"Parser webhook error: {e}")

tg(
    f"✅ <b>Direct Fix применён</b>\n\n"
    f"Изменено:\n" + '\n'.join(f"• {f}" for f in fixes) +
    f"\n\nn8n перезапущен\nДедупликация сброшена\nТест запущен\n\n"
    f"Жди пост в @grandvest_realty через 2 мин!"
)
PYEOF
