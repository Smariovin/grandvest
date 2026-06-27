#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

# Читаем OR ключ из БД
OR_KEY=$(python3 -c "
import sqlite3, json, re
conn = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = conn.cursor()
cur.execute('SELECT nodes FROM workflow_entity')
for (nodes_raw,) in cur.fetchall():
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: print(keys[0]); break
conn.close()
")

echo "OR Key: ${OR_KEY:0:20}..."

# Тест scoring
RESPONSE=$(curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer ${OR_KEY}" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: https://grandvest.ru" \
  -d '{
    "model": "anthropic/claude-sonnet-4-5",
    "max_tokens": 100,
    "messages": [
      {"role": "system", "content": "Оцени релевантность новости для Telegram канала о коммерческой недвижимости Москвы. Ставь высокую оценку (7-10) если новость о: рынке недвижимости, аренде офисов/складов/торговли, инвестициях в недвижимость, девелопменте, строительстве, ипотеке. Отвечай ТОЛЬКО JSON: {\"score\": N, \"reason\": \"краткое объяснение\"}"},
      {"role": "user", "content": "Оцени (1-10):\n\nРынок складской недвижимости Москвы достиг исторического максимума. Вакантность упала до 0.3 процента. Ставки аренды выросли до 12000 рублей за квадратный метр в год. Инвесторы вложили 350 миллиардов рублей в первые пять месяцев 2026 года."}
    ]
  }')

echo "Response: $RESPONSE"
SCORE=$(echo "$RESPONSE" | python3 -c "
import sys,json,re
try:
    d=json.load(sys.stdin)
    content=d['choices'][0]['message']['content']
    print(f'Content: {content!r}')
    try:
        clean=content.strip().replace('\`\`\`json','').replace('\`\`\`','').strip()
        parsed=json.loads(clean)
        print(f'Score: {parsed.get(\"score\",\"?\")}')
    except:
        m=re.search(r'\b([1-9]|10)\b', content)
        print(f'Score(regex): {m.group(1) if m else \"NOT FOUND\"}')
except Exception as e:
    print(f'Error: {e}')
" 2>&1)
echo "$SCORE"

# Отправляем в TG
curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=🔍 Scoring test:
OR Key: ${OR_KEY:0:20}...
$SCORE" > /dev/null
