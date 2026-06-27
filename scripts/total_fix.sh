#!/bin/bash
set -e
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
PAT="${WORKING_PAT}"
DB="/opt/n8n/n8n_data/database.sqlite"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null 2>&1
}

echo "=== TOTAL FIX ==="
echo "PAT: ${PAT:0:15}..."

# 1. Смотрим что сейчас в узле 9
echo "--- Current node9 ---"
python3 -c "
import sqlite3, json, re
conn = sqlite3.connect('$DB')
cur = conn.cursor()
cur.execute(\"SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'\")
nodes = json.loads(cur.fetchone()[0])
conn.close()
for n in nodes:
    name = n.get('name','')
    if 'Отправка' in name or '9.' in name:
        code = n.get('parameters',{}).get('jsCode','')
        tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        print(f'Node: {name}')
        print(f'Tokens: {tokens}')
        print(f'Code preview: {code[:200]}')
"

# 2. Останавливаем n8n
docker stop n8n 2>/dev/null; sleep 3

# 3. Патчим SQLite — заменяем ВСЕ токены на рабочий
python3 << PYEOF
import sqlite3, json, re, os

DB = '$DB'
PAT = os.environ.get('WORKING_PAT', '')
print(f'Using PAT: {PAT[:15]}...')

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Читаем весь nodes JSON как строку и заменяем все ghp_ токены
cur.execute("SELECT id, nodes FROM workflow_entity")
rows = cur.fetchall()

for wf_id, nodes_raw in rows:
    old_tokens = set(re.findall(r'ghp_[A-Za-z0-9]{36,}', nodes_raw))
    old_tokens.discard(PAT)
    if old_tokens:
        new_raw = nodes_raw
        for old in old_tokens:
            new_raw = new_raw.replace(old, PAT)
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?", (new_raw, wf_id))
        print(f'WF {wf_id}: replaced {len(old_tokens)} token(s)')
    else:
        # Активируем в любом случае
        cur.execute("UPDATE workflow_entity SET active=1 WHERE id=?", (wf_id,))

# Очищаем static data (дедупликация по памяти)
cur.execute("UPDATE workflow_entity SET staticData='{}' WHERE 1=1")
conn.commit()
conn.close()

# Сбрасываем файл дедупликации
import os
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json', 'w') as f:
    import json as j
    j.dump([], f)

print('Done! All tokens replaced, staticData cleared, dedup reset.')
PYEOF

# 4. Запускаем n8n
docker start n8n
echo "Waiting for n8n..."
for i in $(seq 1 15); do
    sleep 4
    curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}" && echo "n8n UP!" && break
    echo "  waiting $i..."
done

# 5. Проверяем что токен теперь правильный
echo "--- Node9 after fix ---"
python3 -c "
import sqlite3, json, re, os
PAT = os.environ.get('WORKING_PAT','')
conn = sqlite3.connect('$DB')
cur = conn.cursor()
cur.execute(\"SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'\")
nodes = json.loads(cur.fetchone()[0])
conn.close()
for n in nodes:
    name = n.get('name','')
    if 'Отправка' in name or '9.' in name:
        code = n.get('parameters',{}).get('jsCode','')
        tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        correct = all(t == PAT for t in tokens) if tokens else False
        print(f'Node: {name}')
        print(f'Tokens correct: {correct}')
        print(f'Tokens: {[t[:15] for t in tokens]}')
"

# 6. Живой тест
echo "--- Live test ---"
sleep 5
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Рынок складской недвижимости Москвы и Московской области достиг исторического максимума в 2026 году. Вакантность упала до 0.3 процента. Ставки аренды выросли до 12000 рублей за квадратный метр в год. Дефицит площадей вынуждает арендаторов заключать договоры на объекты на стадии строительства по данным CORE.XP.</div><time datetime=\"2026-06-27T07:00:00+00:00\">07:00</time>"}' \
  && echo "Webhook sent!" || echo "Webhook failed!"

tg "🔧 Total Fix запущен
PAT обновлён во всех узлах
StaticData сброшена
Дедупликация очищена
Тест запущен → жди пост через 2 мин!"

echo "=== DONE ==="
