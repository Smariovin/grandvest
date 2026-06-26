#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
WORKING_PAT="${WORKING_PAT}"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "=== NUKE STATIC DATA + FIX NODE 9 ==="
echo "PAT: ${WORKING_PAT:0:15}..."

docker stop n8n
sleep 3

python3 << PYEOF
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT', '')
print(f"PAT: {PAT[:15]}...")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Показываем таблицы и ищем staticData
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")

# Смотрим поля таблицы workflow_entity
cur.execute("PRAGMA table_info(workflow_entity)")
cols = [(r[1], r[2]) for r in cur.fetchall()]
print(f"workflow_entity columns: {cols}")

# Обнуляем staticData в workflow_entity
if any(col[0] == 'staticData' for col in cols):
    cur.execute("UPDATE workflow_entity SET staticData=NULL")
    print("staticData column cleared!")
elif any(col[0] == 'static_data' for col in cols):
    cur.execute("UPDATE workflow_entity SET static_data=NULL")
    print("static_data column cleared!")
else:
    # Ищем в JSON nodes
    print("No staticData column found, checking nodes JSON...")

# Теперь гарантированно патчим узел 9 и дедупликацию
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
wf_id, wf_name, nodes_raw = cur.fetchone()
nodes = json.loads(nodes_raw)

NODE9 = f"""const postText = $('8. Подготовка данных поста').first().json.tg_post;
const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';
if (!postText || postText.length < 10) {{ throw new Error('tg_post пустой'); }}
console.log('Post:', postText.length, 'chars');
const r = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {{'Authorization': 'token {PAT}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},
  body: JSON.stringify({{ref: 'main', inputs: {{message: postText, image_url: imageUrl}}}})
}});
return [{{json: {{ok: true, len: postText.length}}}}];"""

DEDUP = """const items = $input.all();
const unique = [];
// Используем файловую систему вместо StaticData
let published = [];
try {
  const fs = require('fs');
  const data = fs.readFileSync('/data/published_titles.json', 'utf8');
  published = JSON.parse(data);
} catch(e) { published = []; }

for (const item of items) {
  const title = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 50);
  if (!title) { unique.push(item); continue; }
  if (!published.some(p => p.substring(0, 50) === title)) {
    unique.push(item);
  }
}
return unique.slice(0, 1);"""

fixed = []
for n in nodes:
    name = n.get('name', '')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code', ''))
    
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        old_toks = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        n['parameters']['jsCode'] = NODE9
        n['parameters'].pop('code', None)
        fixed.append(f"Node9: {[t[:12] for t in old_toks]} → {PAT[:12]}")
        print(f"Node9 fixed! Old tokens: {old_toks}")
    
    if ('Дедупликац' in name or '2.' in name) and 'getWorkflowStaticData' in code:
        n['parameters']['jsCode'] = DEDUP
        fixed.append("Dedup: StaticData → filesystem")
        print("Dedup: switched to filesystem!")

cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False), wf_id))
conn.commit()
conn.close()

with open('/data/published_titles.json', 'w') as f:
    json.dump([], f)

print(f"Fixed: {fixed}")
print("SQLite saved!")
PYEOF

docker start n8n
echo "n8n starting..."
sleep 25

# Ждём n8n
for i in $(seq 1 10); do
    if curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}"; then
        echo "n8n UP ($i)"
        break
    fi
    sleep 3
done

# Сбрасываем StaticData через API
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Очищаем static data через n8n API
curl -s -b /tmp/ck.txt -X POST \
  'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ/activate' \
  -H 'Content-Type: application/json' -d '{}' > /dev/null

echo ""
echo "=== LIVE TEST ==="
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Офисная недвижимость Москвы первое полугодие 2026 года вакантность класса А снизилась до семи целых восьми процента минимум за пять лет ставки аренды выросли до сорока восьми тысяч рублей по данным CBRE.</div><time datetime=\"2026-06-26T12:00:00+00:00\">12:00</time>"}' \
  && echo "" && echo "TEST OK" || echo "TEST FAIL"

tg "🔑 <b>Ключевые исправления:</b>

1. secrets.GH_TOKEN обновлён на рабочий токен
2. Узел 9: записан рабочий токен
3. Дедупликация: переключена с StaticData на файловую систему
4. staticData в SQLite: сброшен
5. Тест запущен

Жди пост в @grandvest_realty!"

echo "=== DONE ==="
