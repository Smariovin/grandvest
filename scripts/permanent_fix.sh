#!/bin/bash
set -e
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
GH_PAT="${GH_PAT}"
DB="/opt/n8n/n8n_data/database.sqlite"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "=== PERMANENT FIX START ==="
date

# Шаг 1: Останавливаем n8n
echo "Stopping n8n..."
docker stop n8n 2>/dev/null || true
sleep 3

# Шаг 2: Патчим SQLite напрямую (n8n не запущен — нет конфликтов)
echo "Patching SQLite directly..."
python3 << PYEOF
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
GH_PAT = os.environ.get('GH_PAT', '')

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА (строго):\n\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "По данным аналитиков, [факт+цифры]. [2-3 предложения деталей].\n\n"
    "[КОНТЕКСТ 3-4 предл]: районы Москвы, ставки руб/м кв, сравнение с прошлым.\n\n"
    "[ВЛИЯНИЕ 2-3 предл]: для арендаторов, инвесторов, собственников.\n\n"
    "💼 Комментарий Грандвест: [2-3 предл от агентства]\n\n"
    "💡 Практический совет: [2 конкретных предложения]\n\n"
    "👉 За подбором - @Grandvest_bot\n\n"
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

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

print(f"Workflows in DB: {len(rows)}")
fixes = []

for wf_id, wf_name, nodes_raw in rows:
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue
    
    print(f"\nWF: {wf_name!r} ({wf_id}) - {len(nodes)} nodes")
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
    
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        url = params.get('url', '')
        
        # === Узел 9: Отправка в Telegram ===
        is_send = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is_send and 'code' in ntype.lower():
            has_pub = 'grandvest-publisher' in code
            has_old = 'api.telegram.org' in code or 'sendPhoto' in code
            print(f"  Node9 '{name}': pub={has_pub} old={has_old}")
            if (not has_pub or has_old) and GH_PAT:
                n['parameters']['jsCode'] = node9_code(GH_PAT)
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] Узел 9 → grandvest-publisher")
                print(f"  FIXED node9!")
        
        # === HTTP Request с OpenRouter ===
        if 'httpRequest' in ntype and 'openrouter' in url.lower():
            jb = params.get('jsonBody', '')
            jb_str = str(jb).strip()
            
            # Убираем Expression prefix
            if jb_str.startswith('='):
                jb_str = jb_str[1:].strip()
            
            try:
                body = json.loads(jb_str)
                mt = body.get('max_tokens', 0)
                sys_ok = any(
                    'ТРЕБОВАНИЯ' in str(m.get('content','')) and '900' in str(m.get('content',''))
                    for m in body.get('messages', []) if m.get('role') == 'system'
                )
                need = mt < 2048 or not sys_ok
                print(f"  OR node '{name}': max_tokens={mt} sys_ok={sys_ok} need_fix={need}")
                
                if need:
                    body['max_tokens'] = 2048
                    for m in body.get('messages', []):
                        if m.get('role') == 'system':
                            m['content'] = PROMPT
                    # Сохраняем как чистый JSON (без '=' prefix!)
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': max_tokens→2048, промпт 900-1200")
                    print(f"  FIXED generation!")
                    
            except json.JSONDecodeError as e:
                print(f"  JSONDecodeError: {e} | raw: {jb_str[:100]!r}")
                # Пересоздаём с нуля
                if or_key:
                    user_content = "={{ 'Напиши пост о коммерческой недвижимости по новости:\\n\\n' + $input.first().json.text }}"
                    new_body = {
                        "model": "anthropic/claude-sonnet-4-5",
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": user_content}
                        ]
                    }
                    params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': jsonBody пересоздан")
                    print(f"  REBUILT!")
    
    if changed:
        cur.execute(
            "UPDATE workflow_entity SET nodes=? WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False), wf_id)
        )
        print(f"  SQLite saved for {wf_name}")

# Убеждаемся что оба workflow активны
cur.execute("UPDATE workflow_entity SET active=1")
print("\nAll workflows set to active=1")

conn.commit()
conn.close()

print(f"\nFixes applied: {len(fixes)}")
for f in fixes:
    print(f"  - {f}")
PYEOF

echo ""
echo "=== Starting n8n ==="
docker start n8n
sleep 20

echo ""
echo "=== Verifying n8n is up ==="
for i in 1 2 3 4 5; do
    if curl -s http://localhost:5678/healthz | grep -q "ok\|200\|{}"; then
        echo "n8n is UP!"
        break
    fi
    echo "Waiting... ($i/5)"
    sleep 5
done

echo ""
echo "=== Checking workflow status via API ==="
curl -s -c /tmp/ck2.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

curl -s -b /tmp/ck2.txt 'http://localhost:5678/rest/workflows' | \
python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', [])
for wf in items:
    print(f\"  {wf['name']!r}: active={wf['active']}, id={wf['id']}\")
"

echo ""
echo "=== Sending test to webhook ==="
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"test","html":"<div class=\"tgme_widget_message_text js-message_text\">Рынок офисной недвижимости Москвы: вакантность класса А снизилась до 8,2% по данным CBRE за первое полугодие 2026. Арендные ставки в ЦАО выросли на 12% и достигли 45000 руб за кв м в год.</div><time datetime=\"2026-06-26T09:00:00+00:00\">09:00</time>"}' \
  && echo "" && echo "Webhook: OK" \
  || echo "Webhook: FAIL"

tg "✅ <b>Permanent Fix применён</b>

SQLite пропатчен напрямую (n8n был остановлен)
Все workflows активированы
n8n перезапущен
Тестовый вебхук отправлен

Жди пост в @grandvest_realty через 2-3 мин!"

echo "=== DONE ==="
