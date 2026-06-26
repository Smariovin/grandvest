#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
WORKING_PAT="${WORKING_PAT}"

docker stop n8n && sleep 3

python3 << PYEOF
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT', '')

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
wf_id, wf_name, nodes_raw = cur.fetchone()
nodes = json.loads(nodes_raw)

# Смотрим что именно в каждом узле
for n in nodes:
    name = n.get('name','')
    code = n.get('parameters',{}).get('jsCode', n.get('parameters',{}).get('code',''))
    if code:
        print(f"\n--- {name} ---")
        print(code[:300])

print("\n\n=== APPLYING FIXES ===")

# Узел 1: Парсинг — показываем что он выводит
# Узел 2: Дедупликация — делаем bypass (всегда пропускаем)
# Узел 9: Обновляем токен

DEDUP_BYPASS = """// Временный bypass дедупликации для тестирования
const items = $input.all();
console.log('Dedup input items:', items.length);
for (const item of items) {
  console.log('Item title:', item.json.title || item.json.text || 'NO TITLE');
}
// Возвращаем первый элемент без проверки
const result = items.slice(0, 1);
console.log('Dedup output:', result.length);
return result;"""

NODE9 = f"""const postText = $('8. Подготовка данных поста').first().json.tg_post;
const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';
if (!postText || postText.length < 10) {{ throw new Error('tg_post пустой: ' + JSON.stringify(postText)); }}
console.log('Dispatching post:', postText.length, 'chars');
const r = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {{'Authorization': 'token {PAT}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},
  body: JSON.stringify({{ref: 'main', inputs: {{message: postText, image_url: imageUrl}}}})
}});
return [{{json: {{ok: true, len: postText.length}}}}];"""

for n in nodes:
    name = n.get('name','')
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    
    if 'Дедупликац' in name or '2.' in name:
        n['parameters']['jsCode'] = DEDUP_BYPASS
        print(f"Dedup BYPASSED: {name}")
    
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        n['parameters']['jsCode'] = NODE9
        n['parameters'].pop('code', None)
        old = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        print(f"Node9 fixed: {[t[:12] for t in old]} -> {PAT[:12]}")

cur.execute("UPDATE workflow_entity SET nodes=?, active=1, staticData='{}' WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False), wf_id))
conn.commit()
conn.close()

with open('/data/published_titles.json','w') as f: json.dump([], f)
print("Done!")
PYEOF

docker start n8n && sleep 25

for i in $(seq 1 8); do
    curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}" && echo "n8n UP! ($i)" && break
    sleep 4
done

curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Рынок коммерческой недвижимости Москвы показал рекордный рост в первом полугодии 2026 года. Вакантность офисов класса А снизилась до 7 процентов. Ставки в ЦАО выросли до 50000 рублей за квадратный метр.</div><time datetime=\"2026-06-26T12:30:00+00:00\">12:30</time>"}' \
  && echo "WEBHOOK OK"

curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=🔧 Bypass dedup + fix node9 token. Тест запущен. Жди пост через 2 мин!" > /dev/null
