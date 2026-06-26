#!/bin/bash
GH_PAT="${GH_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

python3 << 'PYEOF'
import sqlite3, json, subprocess, urllib.request, urllib.parse, os, re, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def n8n_login():
    subprocess.run(['curl','-s','-c','/tmp/ck.txt','-X','POST',
        'http://localhost:5678/rest/login','-H','Content-Type: application/json',
        '-d','{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'],
        capture_output=True, timeout=10)

def n8n_get(wf_id):
    r = subprocess.run(['curl','-s','-b','/tmp/ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'],
        capture_output=True, text=True, timeout=15)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

def n8n_put(wf_id, wf):
    r = subprocess.run(['curl','-s','-b','/tmp/ck.txt','-X','PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

# Шаг 1: Читаем ВСЕ данные из SQLite — находим OR ключ и реальную структуру
print("=== STEP 1: Reading all data ===")
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
all_rows = cur.fetchall()
conn.close()

or_key = ''
for _, _, nodes_raw in all_rows:
    found = re.findall(r'sk-or-v1-[a-f0-9]{40,}', nodes_raw)
    if found: or_key = found[0]; break

print(f"OR key: {or_key[:25]}..." if or_key else "OR key: NOT FOUND!")
print(f"GH_PAT: {GH_PAT[:15]}..." if GH_PAT else "GH_PAT: NOT SET!")

for wf_id, wf_name, nodes_raw in all_rows:
    print(f"\nWF: {wf_name!r} ({wf_id})")
    nodes = json.loads(nodes_raw)
    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','').split('.')[-1]
        params = n.get('parameters',{})
        url = params.get('url','')
        code = params.get('jsCode', params.get('code',''))
        jb = params.get('jsonBody','')
        print(f"  [{ntype}] {name!r} url={url[:50]} code_len={len(code)} jb_len={len(str(jb))}")
        if code and len(code) > 10:
            print(f"    code: {code[:100]!r}")
        if jb:
            print(f"    jb: {str(jb)[:100]!r}")

PYEOF

python3 << 'PYEOF2'
import sqlite3, json, subprocess, urllib.request, urllib.parse, os, re, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def n8n_login():
    subprocess.run(['curl','-s','-c','/tmp/ck.txt','-X','POST',
        'http://localhost:5678/rest/login','-H','Content-Type: application/json',
        '-d','{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'],
        capture_output=True, timeout=10)

def n8n_put(wf_id, wf):
    r = subprocess.run(['curl','-s','-b','/tmp/ck.txt','-X','PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
all_rows = cur.fetchall()
conn.close()

or_key = ''
for _, _, nodes_raw in all_rows:
    found = re.findall(r'sk-or-v1-[a-f0-9]{40,}', nodes_raw)
    if found: or_key = found[0]; break

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развернутые посты для Telegram канала Grandvest.\n\n"
    "СТРУКТУРА:\n🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "[ФАКТЫ 3-4 предл: цифры, источники]\n\n"
    "[КОНТЕКСТ 3-4 предл: районы Москвы, ставки руб/кв м, сравнение с прошлым]\n\n"
    "[ВЛИЯНИЕ 2-3 предл: для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предл от агентства]\n\n"
    "💡 Практический совет: [2 конкретных предл]\n\n"
    "👉 За подбором - @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика. Никакой воды."
)

NODE9 = (
    "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
    "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
    "if (!postText || postText.length < 10) { throw new Error('tg_post пустой'); }\n"
    "console.log('Sending:', postText.length, 'chars');\n"
    "const r = await this.helpers.httpRequest({\n"
    "  method: 'POST',\n"
    "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
    f"  headers: {{'Authorization': 'token {GH_PAT}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},\n"
    "  body: JSON.stringify({ref: 'main', inputs: {message: postText, image_url: imageUrl}})\n"
    "});\n"
    "return [{json: {ok: true, len: postText.length}}];"
)

CORRECT_BODY = json.dumps({
    "model": "anthropic/claude-sonnet-4-5",
    "max_tokens": 2048,
    "messages": [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": "={{ 'Напиши пост о коммерческой недвижимости по новости:\\n\\n' + ($input.first().json.text || $input.first().json.title || $input.first().json.description || 'нет данных') }}"}
    ]
}, ensure_ascii=False)

# Логинимся
n8n_login()
print("Logged in to n8n")

fixes = []

# Останавливаем n8n для SQLite патча
subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=30)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue
    changed = False

    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})
        url = params.get('url','')
        code = params.get('jsCode', params.get('code',''))
        jb = params.get('jsonBody','')
        jb_str = str(jb).strip()

        # === УЗЕЛ 9: Отправка ===
        is9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is9:
            # Перезаписываем весь код
            n['parameters']['jsCode'] = NODE9
            n['parameters'].pop('code', None)
            changed = True
            tok_in_code = re.findall(r'ghp_[A-Za-z0-9]+', NODE9)
            fixes.append(f"[{wf_name}] Node9 overwritten (PAT={GH_PAT[:12]})")
            print(f"Node9 overwritten: {name!r}")

        # === OpenRouter HTTP Request ===
        if 'httpRequest' in ntype and 'openrouter' in url.lower():
            # Убираем = prefix и пересоздаём
            clean = jb_str[1:] if jb_str.startswith('=') else jb_str
            try:
                body = json.loads(clean)
                mt = body.get('max_tokens',0)
                sys_ok = any('ТРЕБОВАНИЯ' in str(m.get('content',''))
                    for m in body.get('messages',[]) if m.get('role')=='system')
                if mt < 2048 or not sys_ok:
                    body['max_tokens'] = 2048
                    for m in body.get('messages',[]):
                        if m.get('role') == 'system': m['content'] = PROMPT
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': mt→2048")
                    print(f"OR fixed: {name!r} mt={mt}→2048")
            except:
                # Пересоздаём полностью
                params['jsonBody'] = CORRECT_BODY
                params['specifyBody'] = 'json'
                params['bodyContentType'] = 'json'
                params['sendBody'] = True
                n['parameters'] = params
                changed = True
                fixes.append(f"[{wf_name}] '{name}': rebuilt")
                print(f"OR rebuilt: {name!r}")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))

cur.execute("UPDATE workflow_entity SET active=1")
conn.commit()
conn.close()
print(f"\nFixes: {fixes}")

# Запускаем n8n
subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=30)
time.sleep(25)

# Проверяем здоровье
for i in range(6):
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except:
        print(f"waiting n8n... {i+1}/6")
        time.sleep(5)

# Сбрасываем дедупликацию
with open('/data/published_titles.json', 'w') as f:
    json.dump([], f)
print("Dedup reset")

# Ждём пока n8n прогрузится
time.sleep(10)

# Логинимся снова после рестарта
n8n_login()

# Отправляем тест
try:
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': '<div class="tgme_widget_message_text js-message_text">Офисная недвижимость Москвы Q2 2026: вакантность класса А опустилась до 7.8 процента. В ЦАО ставки аренды выросли до 48000 рублей за квадратный метр в год. IT-компании заключили 34 процента от общего объема сделок по данным CBRE.</div><time datetime="2026-06-26T11:00:00+00:00">11:00</time>'
    }).encode()
    urllib.request.urlopen(
        urllib.request.Request('http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type': 'application/json'}), timeout=30)
    print("Test webhook sent!")
except Exception as e:
    print(f"Webhook error: {e}")

tg(
    f"✅ <b>Total Rebuild завершён</b>\n\n"
    + '\n'.join(f"• {f}" for f in fixes) +
    "\n\nn8n перезапущен\nДедупликация сброшена\nТест запущен\n\nЖди пост!"
)
PYEOF2
