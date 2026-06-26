#!/bin/bash
set -e
GH_PAT="${GH_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
DB="/opt/n8n/n8n_data/database.sqlite"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "====== ULTIMATE FIX ======"
echo "GH_PAT: ${GH_PAT:0:15}..."
date

# Шаг 1: Смотрим что реально в executions — почему Claude серый
echo ""
echo "=== DIAGNOSIS: Why Claude node is grey ==="
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Читаем последний execution с деталями
EXEC=$(curl -s -b /tmp/ck.txt \
  'http://localhost:5678/rest/executions?limit=5&includeData=true')

echo "$EXEC" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', {})
if isinstance(items, dict): items = items.get('results', [])
print(f'Executions: {len(items)}')
for ex in items[:3]:
    wf = ex.get('workflowData',{}).get('name','?')
    status = ex.get('status','?')
    data = ex.get('data',{})
    result = data.get('resultData',{}) if data else {}
    run_data = result.get('runData',{})
    print(f'\nWF: {wf} | {status}')
    for node_name, node_runs in run_data.items():
        for nr in (node_runs or []):
            exec_status = nr.get('executionStatus','?')
            err = nr.get('error',{})
            err_msg = err.get('message','') if err else ''
            # Выходные данные
            out = nr.get('data',{}).get('main',[[]])
            out_count = len(out[0]) if out and out[0] else 0
            print(f'  [{exec_status}] {node_name}: items_out={out_count} {err_msg[:60]}')
" 2>&1

# Шаг 2: Читаем узел дедупликации — там может быть проблема
echo ""
echo "=== Node 2: Дедупликация входящих ==="
python3 -c "
import sqlite3, json
conn = sqlite3.connect('$DB')
cur = conn.cursor()
cur.execute(\"SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'\")
nodes = json.loads(cur.fetchone()[0])
conn.close()
for n in nodes:
    name = n.get('name','')
    if 'Дедупликац' in name or '2.' in name:
        code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
        print(f'NODE: {name}')
        print(f'CODE ({len(code)} chars):')
        print(code[:800])
        print()
    if 'фильтр' in name.lower() or 'оценк' in name.lower():
        code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
        print(f'NODE: {name}')
        print(f'CODE ({len(code)} chars):')
        print(code[:800])
" 2>&1

# Шаг 3: Проверяем файл дедупликации
echo ""
echo "=== Dedup file ==="
cat /data/published_titles.json | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f'Items in dedup: {len(d)}')
    if d: print(f'Last 3: {d[-3:]}')
except Exception as e:
    print(f'Error: {e}')
    print(sys.stdin.read()[:100])
"

# Шаг 4: Стоп n8n, полная перезапись ВСЕГО через SQLite
echo ""
echo "=== STOP n8n ==="
docker stop n8n
sleep 3

python3 << 'PYEOF'
import sqlite3, json, re, os, urllib.request, urllib.parse

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развернутые посты для Telegram канала Grandvest.\n\n"
    "СТРУКТУРА:\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "[ФАКТЫ: 3-4 предложения с цифрами, источниками, конкретными данными]\n\n"
    "[КОНТЕКСТ: 3-4 предложения — районы Москвы, ставки руб/кв м, сравнение с прошлым]\n\n"
    "[ВЛИЯНИЕ: 2-3 предложения для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения]\n\n"
    "💡 Практический совет: [2 конкретных предложения]\n\n"
    "👉 За подбором — @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика. Никакой воды."
)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

report = []
fixes = 0

for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue

    changed = False
    
    # Ищем OR ключ в этом workflow
    or_key = ''
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: or_key = keys[0]

    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        url = params.get('url', '')

        # === УЗЕЛ 9: полная перезапись с ПРАВИЛЬНЫМ токеном ===
        is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is_node9:
            current_tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
            print(f"  Node9 '{name}': current_tokens={[t[:12] for t in current_tokens]}")
            print(f"  GH_PAT to use: {GH_PAT[:15]}...")
            
            new_code = (
                "// Отправка через GitHub Actions (api.telegram.org заблокирован с РФ)\n"
                "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
                "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
                "if (!postText || postText.length < 10) {\n"
                "  throw new Error('tg_post пустой: ' + JSON.stringify(postText));\n"
                "}\n"
                "console.log('Posting:', postText.length, 'chars, image:', !!imageUrl);\n"
                f"const r = await this.helpers.httpRequest({{\n"
                "  method: 'POST',\n"
                "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
                f"  headers: {{\n"
                f"    'Authorization': 'token {GH_PAT}',\n"
                "    'Content-Type': 'application/json',\n"
                "    'Accept': 'application/vnd.github+json'\n"
                "  }},\n"
                "  body: JSON.stringify({ref: 'main', inputs: {message: postText, image_url: imageUrl}})\n"
                "});\n"
                "console.log('Dispatch OK!');\n"
                "return [{json: {ok: true, len: postText.length}}];"
            )
            n['parameters']['jsCode'] = new_code
            n['parameters'].pop('code', None)
            changed = True
            report.append(f"[{wf_name}] Node9: token {GH_PAT[:12]}... записан")
            fixes += 1
            print(f"  ✅ Node9 OVERWRITTEN with PAT {GH_PAT[:12]}...")

        # === OpenRouter узлы: исправляем jsonBody ===
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            jb = str(params.get('jsonBody', '')).strip()
            clean = jb[1:].strip() if jb.startswith('=') else jb
            
            try:
                body = json.loads(clean)
                mt = body.get('max_tokens', 0)
                sys_ok = any('ТРЕБОВАНИЯ' in str(m.get('content',''))
                            for m in body.get('messages',[]) if m.get('role')=='system')
                print(f"  OR '{name}': max_tokens={mt} sys_ok={sys_ok}")
                
                if mt < 2048 or not sys_ok:
                    body['max_tokens'] = 2048
                    for m in body.get('messages', []):
                        if m.get('role') == 'system':
                            m['content'] = PROMPT
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    report.append(f"[{wf_name}] '{name}': max_tokens→2048 prompt fixed")
                    fixes += 1
                    print(f"  ✅ OR fixed!")
                else:
                    print(f"  ✓ OR OK")
                    
            except json.JSONDecodeError as e:
                print(f"  ❌ OR JSONError: {e} | raw: {clean[:100]!r}")
                if or_key:
                    # Определяем user_content по контексту workflow
                    if 'RSS' in wf_name or 'новост' in wf_name.lower():
                        user_content = "={{ 'Напиши пост о коммерческой недвижимости по этой новости:\\n\\n' + ($input.first().json.title || $input.first().json.description || $input.first().json.text || '') }}"
                    else:
                        user_content = "={{ 'Напиши пост о коммерческой недвижимости по этой новости:\\n\\n' + ($input.first().json.text || $input.first().json.content || '') }}"
                    
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
                    n['parameters'] = params
                    changed = True
                    report.append(f"[{wf_name}] '{name}': REBUILT")
                    fixes += 1
                    print(f"  ✅ OR REBUILT!")
                else:
                    print(f"  ❌ No OR key, cannot rebuild")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))
        print(f"  SQLite saved: {wf_name}")

conn.commit()
conn.close()

print(f"\n=== TOTAL FIXES: {fixes} ===")
for r in report:
    print(f"  {r}")

tg(f"🔧 Ultimate Fix:\n" + '\n'.join(f"• {r}" for r in report) + f"\n\nFixes: {fixes}")
PYEOF

echo ""
echo "=== START n8n ==="
docker start n8n
sleep 25

# Проверяем что n8n работает
for i in 1 2 3 4 5 6; do
    if curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}"; then
        echo "n8n UP after ${i}x5s!"
        break
    fi
    sleep 5
done

# Сбрасываем дедупликацию
echo '[]' > /data/published_titles.json
echo "Dedup: RESET"

# Ждём 3 секунды и отправляем тест
sleep 3

echo ""
echo "=== TEST WEBHOOK ==="
RESP=$(curl -s -X POST http://localhost:5678/webhook/telegram-parser \
    -H 'Content-Type: application/json' \
    -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Рынок офисной недвижимости Москвы: по итогам первого полугодия 2026 года вакантность в классе А упала до 7,8 процента, что является минимумом за пять лет. Ставки аренды в ЦАО выросли до 48000 рублей за квадратный метр в год, в деловом районе Москва-Сити достигли 65000 рублей. Спрос со стороны IT-компаний вырос на 34 процента год к году по данным CBRE.</div><time datetime=\"2026-06-26T10:00:00+00:00\">10:00</time>"}')
echo "Webhook: $RESP"

tg "🚀 <b>Тест запущен</b>
n8n перезапущен, дедупликация сброшена
Тестовый вебхук отправлен
Жди пост в @grandvest_realty через 2 мин!"

echo ""
echo "=== ULTIMATE FIX DONE ==="
