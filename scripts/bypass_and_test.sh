#!/bin/bash
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
DB="/opt/n8n/n8n_data/database.sqlite"

docker stop n8n && sleep 3

python3 << PYEOF
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT', '')

# Промпт генерации
PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы. "
    "Напиши развёрнутый пост для Telegram канала Grandvest.\n\n"
    "СТРУКТУРА:\n🏢 [ЗАГОЛОВОК]\n\n[ФАКТЫ с цифрами]\n\n"
    "[КОНТЕКСТ: районы, ставки]\n\n[ВЛИЯНИЕ на рынок]\n\n"
    "💼 Комментарий Грандвест:\n\n💡 Совет:\n\n"
    "👉 @Grandvest_bot\n#коммерческаянедвижимость #москва\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов."
)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
wf_id, wf_name, nodes_raw = cur.fetchone()
nodes = json.loads(nodes_raw)
or_key = ''
keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
if keys: or_key = keys[0]

print(f"OR key: {or_key[:20]}...")
print(f"PAT: {PAT[:15]}...")

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    url = params.get('url','')

    # Узел 9
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        new_code = (
            "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
            "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
            "if (!postText || postText.length < 10) { throw new Error('tg_post пустой'); }\n"
            f"const r = await this.helpers.httpRequest({{\n"
            "  method: 'POST',\n"
            "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
            f"  headers: {{'Authorization': 'token {PAT}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},\n"
            "  body: JSON.stringify({ref: 'main', inputs: {message: postText, image_url: imageUrl}})\n"
            "});\n"
            "return [{json: {ok: true, len: postText.length}}];"
        )
        n['parameters']['jsCode'] = new_code
        n['parameters'].pop('code', None)
        print(f"✅ Node9: PAT {PAT[:12]}...")

    # Фильтр оценки — BYPASS (всегда пропускает)
    if 'фильтр' in name.lower():
        bypass = """// Bypass: пропускаем все новости о недвижимости
const content = $input.first().json.choices?.[0]?.message?.content || '';
let score = 7; // Default высокий score
try {
  let cleaned = content.trim().replace(/```(?:json)?\\s*/gi, '').replace(/```/g, '').trim();
  if (cleaned.startsWith('{')) {
    const parsed = JSON.parse(cleaned);
    score = parseInt(parsed.score) || 7;
  }
} catch(e) { score = 7; }
console.log('Score (bypass mode):', score);
// Всегда пропускаем если есть хоть какой-то score
const src = $('2. Дедупликация входящих').first().json;
return [{ json: { ...src, score } }];"""
        n['parameters']['jsCode'] = bypass
        print(f"✅ Filter: BYPASS mode (always pass)")

    # Дедупликация
    if ('Дедупликац' in name or '2.' in name):
        dedup = """const items = $input.all();
const unique = [];
let published = [];
try {
  const fs = require('fs');
  published = JSON.parse(fs.readFileSync('/data/published_titles.json', 'utf8'));
} catch(e) { published = []; }
for (const item of items) {
  const text = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 60);
  if (!published.some(p => p.substring(0, 60) === text)) {
    unique.push(item);
  }
}
console.log('Dedup:', items.length, '->', unique.length, 'items');
return unique.slice(0, 1);"""
        n['parameters']['jsCode'] = dedup
        print(f"✅ Dedup: filesystem mode")

    # OpenRouter генерация
    if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
        jb = str(params.get('jsonBody','')).strip()
        clean = jb[1:].strip() if jb.startswith('=') else jb
        try:
            body = json.loads(clean) if clean else {}
            mt = body.get('max_tokens', 0)
            if mt < 2048:
                body['max_tokens'] = 2048
                for m in body.get('messages',[]):
                    if m.get('role')=='system' and 'генерац' in name.lower():
                        m['content'] = PROMPT
                params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                n['parameters'] = params
                print(f"✅ OR '{name}': max_tokens {mt}->2048")
        except Exception as e:
            print(f"⚠️  OR '{name}': {e}")

cur.execute("UPDATE workflow_entity SET nodes=?, active=1, staticData='{}' WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False), wf_id))
conn.commit()
conn.close()

import os
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)
print("✅ All patched! Dedup reset!")
PYEOF

docker start n8n
echo "Starting n8n..."
for i in $(seq 1 12); do
    sleep 5
    curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}" && echo "n8n UP! ($i)" && break
done

sleep 5
# Тест
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Складской рынок Москвы 2026: вакантность снизилась до рекордных 0.3 процента. Ставки аренды достигли 12000 рублей за кв м в год. Объем инвестиций составил 350 миллиардов рублей. Дефицит площадей вынуждает арендаторов бронировать объекты за 2 года до ввода по данным NF Group.</div><time datetime=\"2026-06-27T08:00:00+00:00\">08:00</time>"}' \
  && echo "Webhook OK"

curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=✅ Bypass mode ON
Фильтр оценки: всегда пропускает (bypass)
Дедупликация: файловая система
Узел 9: токен ${PAT:0:12}...
Тест запущен → жди пост в @grandvest_realty!" > /dev/null

echo "=== DONE ==="
