#!/bin/bash
# Исправляем порог оценки и промпт Claude для оценки
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
WORKING_PAT="${WORKING_PAT}"

docker stop n8n && sleep 3

python3 << 'PYEOF'
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT','')

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
wf_id, wf_name, nodes_raw = cur.fetchone()
nodes = json.loads(nodes_raw)

# Новый промпт для Claude — оценки новостей недвижимости
CLAUDE_SCORING_BODY = json.dumps({
    "model": "anthropic/claude-sonnet-4-5",
    "max_tokens": 100,
    "messages": [
        {
            "role": "system",
            "content": (
                "Ты оцениваешь новости о недвижимости для Telegram канала агентства Grandvest (Москва). "
                "Оцени релевантность новости по шкале 1-10. "
                "Ставь оценку >= 6 если новость касается: рынка недвижимости России/Москвы, "
                "аренды, покупки, строительства, инвестиций в недвижимость, ипотеки, девелопмента, "
                "коммерческой или жилой недвижимости, застройщиков, риелторов. "
                "Ставь оценку < 6 только если новость совсем не связана с недвижимостью. "
                "Отвечай ТОЛЬКО JSON: {\"score\": N, \"reason\": \"краткое объяснение\"}"
            )
        },
        {
            "role": "user",
            "content": "={{ 'Оцени релевантность этой новости для канала о недвижимости:\\n\\n' + $input.first().json.text }}"
        }
    ]
}, ensure_ascii=False)

# Новый код фильтра — снижаем порог до 4 и улучшаем парсинг
NEW_FILTER_CODE = """const content = $input.first().json.choices?.[0]?.message?.content || '';
let score = 0;
try {
  let cleaned = content.trim();
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.replace(/^```(?:json)?\\s*/i, '').replace(/\\s*```$/, '').trim();
  }
  const parsed = JSON.parse(cleaned);
  score = parseInt(parsed.score) || 0;
} catch(e) {
  const numMatch = content.match(/\\b([1-9]|10)\\b/);
  score = numMatch ? parseInt(numMatch[1]) : (content.trim().length > 0 ? 5 : 0);
}

console.log('Score:', score, 'Content:', content.substring(0, 100));

if (score >= 4) {
  const src = $('2. Дедупликация входящих').first().json;
  return [{ json: { ...src, score } }];
}

return [];"""

or_key = ''
fixed = []
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    url = params.get('url','')

    # Фиксим порог фильтра оценки
    if 'фильтр' in name.lower() and 'code' in ntype.lower():
        print(f"Fixing filter threshold: {name}")
        n['parameters']['jsCode'] = NEW_FILTER_CODE
        fixed.append(f"Фильтр: порог снижен с 6 до 4")

    # Улучшаем промпт Claude для оценки
    if 'Claude' in name and 'httpRequest' in ntype and 'openrouter' in url.lower():
        print(f"Fixing Claude scoring prompt: {name}")
        params['jsonBody'] = CLAUDE_SCORING_BODY
        n['parameters'] = params
        fixed.append(f"Claude оценка: улучшен промпт")
        # Сохраняем OR ключ
        h_params = params.get('headerParameters',{}).get('parameters',[])
        for h in h_params:
            v = str(h.get('value',''))
            if 'sk-or' in v: or_key = v.replace('Bearer ','').strip()

    # Фиксим узел 9
    if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
        old_tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        if old_tokens or 'grandvest-publisher' not in code:
            node9_code = (
                "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
                "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
                "if (!postText || postText.length < 10) { throw new Error('tg_post пустой'); }\n"
                "console.log('Posting:', postText.length, 'chars');\n"
                f"const r = await this.helpers.httpRequest({{\n"
                "  method: 'POST',\n"
                "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
                f"  headers: {{'Authorization': 'token {PAT}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},\n"
                "  body: JSON.stringify({ref: 'main', inputs: {message: postText, image_url: imageUrl}})\n"
                "});\n"
                "return [{json: {ok: true, len: postText.length}}];"
            )
            n['parameters']['jsCode'] = node9_code
            n['parameters'].pop('code', None)
            fixed.append(f"Узел 9: токен {PAT[:12]}...")
            print(f"Node9 fixed with PAT {PAT[:12]}")

cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False), wf_id))

# Очищаем статик дату
cur.execute("UPDATE workflow_entity SET staticData='{}' WHERE id='F24jvKiXJIs4wRiZ'")

conn.commit()
conn.close()

# Сбрасываем деdup файл
with open('/data/published_titles.json','w') as f: json.dump([], f)

print(f"\nFixed: {fixed}")
print("Done!")
PYEOF

docker start n8n
echo "n8n starting..."
sleep 25

for i in $(seq 1 10); do
    curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}" && echo "n8n UP ($i)" && break
    sleep 3
done

# Тест с реальной новостью о недвижимости
echo ""
echo "=== LIVE TEST ==="
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">ГК ПИК вводит в эксплуатацию жилой комплекс Мироново в Москве площадью 120000 квадратных метров. Продажи квартир начнутся в третьем квартале 2026 года. Стоимость квадратного метра от 250000 рублей. Комплекс расположен в Северо-Восточном административном округе рядом со станцией метро Ботанический сад.</div><time datetime=\"2026-06-26T18:00:00+00:00\">18:00</time>"}' \
  && echo "" && echo "Webhook OK"

curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=✅ Score fix applied!
• Порог снижен с 6 до 4
• Промпт Claude оценки улучшен  
• Узел 9: рабочий токен записан
• Тест запущен с реальной новостью о ПИК
Жди пост в @grandvest_realty через 2 мин!" > /dev/null

echo "DONE"
