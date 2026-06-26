#!/bin/bash
# Master Fix: исправляет ВСЁ за один запуск
# 1. Читает реальный ID RSS workflow
# 2. Патчит узел генерации (убирает Expression, ставит чистый JSON)
# 3. Патчит RSS HTTP Request6
# 4. Отправляет полный отчёт в TG

BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
GH_PAT="${GH_PAT}"

tg_send() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "=== Login ==="
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null
echo "OK"

echo ""
echo "=== Get all workflow IDs ==="
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows' | \
python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', [])
print(f'Total: {len(items)}')
for wf in items:
    print(f'ID={wf[\"id\"]} | name={wf[\"name\"]!r} | active={wf[\"active\"]}')
"

echo ""
echo "=== Fix both workflows ==="
curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows' | \
python3 << 'PYEOF'
import sys, json, subprocess, os

GH_PAT = os.environ.get('GH_PAT', '')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

import urllib.request, urllib.parse

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def n8n_get(wf_id):
    r = subprocess.run(['curl','-s','-b','/tmp/ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'],
        capture_output=True, text=True, timeout=15)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except: return {}

def n8n_put(wf_id, wf_data):
    r = subprocess.run(['curl','-s','-b','/tmp/ck.txt','-X','PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf_data, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except: return {}

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА (строго):\n\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "По данным аналитиков, [факт+цифры]. [2-3 предложения деталей].\n\n"
    "[КОНТЕКСТ 3-4 предл]: районы Москвы, ставки руб/м², сравнение с прошлым.\n\n"
    "[ВЛИЯНИЕ 2-3 предл]: для арендаторов, инвесторов, собственников.\n\n"
    "💼 Комментарий Грандвест: [2-3 предл от агентства]\n\n"
    "💡 Практический совет: [2 конкретных предложения]\n\n"
    "👉 За подбором — @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика. Никакой воды."
)

def node9_code(pat):
    return (
        "// Отправка через GitHub Actions (api.telegram.org заблокирован с РФ)\n"
        "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
        "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
        "if (!postText || postText.length < 10) { throw new Error('tg_post пустой'); }\n"
        "console.log('Post:', postText.length, 'chars');\n"
        "const r = await this.helpers.httpRequest({\n"
        "  method: 'POST',\n"
        "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
        f"  headers: {{'Authorization': 'token {pat}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},\n"
        "  body: JSON.stringify({ref: 'main', inputs: {message: postText, image_url: imageUrl}})\n"
        "});\n"
        "return [{json: {ok: true, len: postText.length}}];"
    )

# Читаем все workflows
d = json.load(sys.stdin)
all_wfs = d.get('data', [])
print(f"Total workflows: {len(all_wfs)}")

fixes = []
errors = []

for wf_info in all_wfs:
    wf_id = wf_info['id']
    wf_name = wf_info['name']
    print(f"\n{'='*50}")
    print(f"WF: {wf_name!r} ({wf_id})")

    wf = n8n_get(wf_id)
    nodes = wf.get('nodes', [])
    print(f"Nodes: {len(nodes)}")
    changed = False

    # Ищем OR ключ в этом workflow
    or_key = ''
    for n in nodes:
        params = n.get('parameters', {})
        headers = params.get('headerParameters', {}).get('parameters', [])
        for h in headers:
            v = str(h.get('value', ''))
            if 'sk-or-v1' in v:
                or_key = v.replace('Bearer ', '').strip()
                print(f"  Found OR key: {or_key[:20]}...")

    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        url = params.get('url', '')

        # === Узел отправки в Telegram (узел 9) ===
        is_sending = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is_sending and ntype == 'n8n-nodes-base.code':
            has_pub = 'grandvest-publisher' in code
            has_old = 'api.telegram.org' in code or 'sendPhoto' in code
            print(f"  Node9 '{name}': pub={has_pub} old={has_old}")
            if not has_pub or has_old:
                if GH_PAT:
                    n['parameters']['jsCode'] = node9_code(GH_PAT)
                    n['parameters'].pop('code', None)
                    changed = True
                    fixes.append(f"[{wf_name}] Узел 9 → grandvest-publisher.yml")
                    print(f"  → FIXED node9!")

        # === HTTP Request узлы с OpenRouter ===
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            print(f"  OR node: '{name}'")
            jb = params.get('jsonBody', '')
            jb_str = str(jb).strip()

            # Ключевое: если начинается с '=' — это Expression, убираем
            if jb_str.startswith('='):
                jb_str = jb_str[1:].strip()
                print(f"  Stripped '=' prefix")

            # Парсим
            try:
                body = json.loads(jb_str)
                mt = body.get('max_tokens', 0)
                need_fix = mt < 2048
                sys_ok = False
                for msg in body.get('messages', []):
                    if msg.get('role') == 'system':
                        c = msg.get('content', '')
                        sys_ok = 'ТРЕБОВАНИЯ' in c and '900' in c
                need_fix = need_fix or not sys_ok

                print(f"  max_tokens={mt} sys_ok={sys_ok} need_fix={need_fix}")

                if need_fix:
                    body['max_tokens'] = 2048
                    for msg in body.get('messages', []):
                        if msg.get('role') == 'system':
                            msg['content'] = PROMPT
                    # Сохраняем БЕЗ prefix '='
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': max_tokens→2048, промпт расширен")
                    print(f"  → FIXED generation!")

            except json.JSONDecodeError as e:
                print(f"  JSONDecodeError: {e}")
                print(f"  jb_str: {jb_str[:200]!r}")
                # Строим с нуля если OR ключ есть
                if or_key:
                    new_body = {
                        "model": "anthropic/claude-sonnet-4-5",
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": "={{ 'Напиши пост о коммерческой недвижимости по новости:\\n\\n' + $input.first().json.text }}"}
                        ]
                    }
                    params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': jsonBody пересоздан")
                    print(f"  → REBUILT from scratch!")
                else:
                    errors.append(f"[{wf_name}] '{name}': нет OR ключа для пересоздания")

    if changed:
        print(f"\n  Saving {wf_name}...")
        result = n8n_put(wf_id, wf)
        cnt = len(result.get('nodes', []))
        print(f"  Saved! {cnt} nodes")

print(f"\n{'='*50}")
print(f"FIXES: {fixes}")
print(f"ERRORS: {errors}")

if fixes or errors:
    msg = ""
    if fixes:
        msg += "✅ <b>Master Fix применён:</b>\n" + '\n'.join(f"• {f}" for f in fixes)
    if errors:
        msg += "\n\n⚠️ <b>Требует внимания:</b>\n" + '\n'.join(f"• {e}" for e in errors)
    tg(msg)
PYEOF

echo ""
echo "=== DONE ==="
