#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
# Рабочий токен передаём напрямую через env
WORKING_PAT="${WORKING_PAT}"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "=== FINAL REAL FIX ==="
echo "Working PAT: ${WORKING_PAT:0:15}..."

# Шаг 1: Останавливаем n8n
echo "Stopping n8n..."
docker stop n8n
sleep 3

# Шаг 2: Патчим SQLite — узел 9 с правильным токеном + сбрасываем статику
python3 << PYEOF
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
WORKING_PAT = os.environ.get('WORKING_PAT', '')
print(f"Using PAT: {WORKING_PAT[:15]}...")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Показываем все таблицы
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")

# Сбрасываем workflow static data (там хранится publishedTitles)
for table in tables:
    if 'static' in table.lower() or 'data' in table.lower():
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"Table {table}: {count} rows")
            if count > 0:
                cur.execute(f"SELECT * FROM {table} LIMIT 3")
                for row in cur.fetchall():
                    print(f"  Sample: {str(row)[:100]}")
        except Exception as e:
            print(f"  Table {table} error: {e}")

# Очищаем workflow_statistics и static data
for table in ['workflow_statistics', 'workflow_entity']:
    if table == 'workflow_statistics' and table in tables:
        cur.execute("DELETE FROM workflow_statistics")
        print(f"Cleared {table}")

# Обновляем узел 9 во всех workflows
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

NODE9_CODE = f"""// Отправка в Telegram через GitHub Actions
const postText = $('8. Подготовка данных поста').first().json.tg_post;
const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';
if (!postText || postText.length < 10) {{
  throw new Error('tg_post пустой: ' + JSON.stringify(postText));
}}
console.log('Posting:', postText.length, 'chars');
const r = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {{
    'Authorization': 'token {WORKING_PAT}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github+json'
  }},
  body: JSON.stringify({{ref: 'main', inputs: {{message: postText, image_url: imageUrl}}}})
}});
console.log('GitHub dispatch OK');
return [{{json: {{ok: true, len: postText.length}}}}];"""

# Также исправляем дедупликацию — убираем использование publishedTitles из static data
# Заменяем на файловую систему
DEDUP_CODE = """const items = $input.all();
const unique = [];
const fs = require('fs');
const DEDUP_FILE = '/data/published_titles.json';

let published = [];
try {
  published = JSON.parse(fs.readFileSync(DEDUP_FILE, 'utf8'));
} catch(e) {
  published = [];
}

for (const item of items) {
  const title = item.json.title?.trim().toLowerCase();
  if (!title) continue;
  const titleShort = title.substring(0, 50);
  const hasSimilar = published.some(p => p.substring(0, 50) === titleShort);
  if (hasSimilar) continue;
  unique.push(item);
}

return unique.slice(0, 1);"""

for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue
    
    changed = False
    for n in nodes:
        name = n.get('name', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        
        # Патч узла 9
        is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is_node9:
            tokens_before = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
            n['parameters']['jsCode'] = NODE9_CODE
            n['parameters'].pop('code', None)
            changed = True
            print(f"Node9 [{wf_name}] '{name}': {[t[:12] for t in tokens_before]} -> {WORKING_PAT[:12]}...")
        
        # Патч дедупликации — убираем getWorkflowStaticData
        if ('Дедупликац' in name or '2.' in name) and 'getWorkflowStaticData' in code:
            n['parameters']['jsCode'] = DEDUP_CODE
            changed = True
            print(f"Dedup [{wf_name}] '{name}': switched from StaticData to file system")
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))
        print(f"Saved: {wf_name}")

# Очищаем файл дедупликации
with open('/data/published_titles.json', 'w') as f:
    json.dump([], f)
print("Dedup file: cleared")

conn.commit()
conn.close()
print("SQLite done!")
PYEOF

# Шаг 3: Запускаем n8n
echo ""
echo "Starting n8n..."
docker start n8n

# Ждём запуска
for i in 1 2 3 4 5 6 7 8; do
    sleep 5
    if curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}"; then
        echo "n8n UP! (${i}x5s)"
        break
    fi
    echo "Waiting... $i"
done

# Шаг 4: Сбрасываем Static Data через n8n API
echo ""
echo "Resetting workflow static data via API..."
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Сбрасываем static data для workflow F24jvKiXJIs4wRiZ
curl -s -b /tmp/ck.txt -X POST \
  'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ/static-data' \
  -H 'Content-Type: application/json' \
  -d '{}' 2>/dev/null || true

# Альтернатива — через PATCH
curl -s -b /tmp/ck.txt -X PATCH \
  'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' \
  -H 'Content-Type: application/json' \
  -d '{"staticData": null}' 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    wf=d.get('data',d)
    sd=wf.get('staticData','?')
    print(f'staticData after reset: {sd}')
except: print('reset response:', sys.stdin.read()[:100])
" 2>/dev/null || true

echo ""
echo "=== LIVE TEST ==="
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Офисная недвижимость Москвы: по итогам первого полугодия 2026 года вакантность класса А упала до 7,8 процента — минимум за пять лет. Ставки аренды в ЦАО выросли до 48000 рублей за квадратный метр в год, в Москва-Сити достигли 65000 рублей. IT-компании обеспечили 34 процента сделок по данным CBRE.</div><time datetime=\"2026-06-26T11:30:00+00:00\">11:30</time>"}' \
  && echo "Webhook: OK" || echo "Webhook: FAIL"

tg "✅ <b>Final Real Fix</b>

1. Узел 9: токен заменён на рабочий
2. Дедупликация: переключена на файловую систему (убран getWorkflowStaticData)
3. Static data: сброшена через API
4. Деdup файл очищен
5. n8n перезапущен
6. Тест запущен

Жди пост в @grandvest_realty через 2 мин!"

echo "=== DONE ==="
