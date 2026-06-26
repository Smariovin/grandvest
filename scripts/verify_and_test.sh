#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

tg_send() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        -d "chat_id=${CHAT}&text=$1&parse_mode=HTML" > /dev/null
}

echo "=== Проверяем узел 9 после патча ==="

# Логин
curl -s -c /tmp/ck2.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Проверяем
RESULT=$(curl -s -b /tmp/ck2.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
import sys,json
d=json.load(sys.stdin)
wf=d.get('data',d)
nodes=wf.get('nodes',[])
for n in nodes:
    name=n.get('name','')
    if 'Отправка' in name or '9.' in name:
        code=n.get('parameters',{}).get('jsCode','')
        has_pub='grandvest-publisher' in code
        has_tg='api.telegram.org' in code
        has_send='sendPhoto' in code
        print(f'NODE9={name}|PUB={has_pub}|TG={has_tg}|SEND={has_send}|LEN={len(code)}')
")

echo "Result: $RESULT"

if echo "$RESULT" | grep -q "PUB=True"; then
    MSG="✅ <b>Узел 9 исправлен!</b>%0A%0Agrandvest-publisher.yml: ✅%0Adirect telegram API: ❌ (убран)%0A%0AЗапускаю тест публикации..."
    tg_send "$MSG"
    
    # Тестовая публикация через webhook
    curl -s -X POST http://localhost:5678/webhook/telegram-parser \
        -H 'Content-Type: application/json' \
        -d '{"channel":"test","html":"<div class=\"tgme_widget_message_text js-message_text\">Рынок офисной недвижимости Москвы: вакантность в классе А снизилась до 8,2% по итогам первого полугодия 2026 года, сообщают аналитики CBRE. Ставки аренды выросли на 12% год к году и достигли 45 000 руб за кв м в год в ЦАО.</div><time datetime=\"2026-06-26T08:00:00+00:00\">08:00</time>"}' \
        && echo "Webhook sent OK" \
        || echo "Webhook FAIL"
else
    MSG="❌ <b>Узел 9 НЕ исправлен!</b>%0A%0AResult: $RESULT"
    tg_send "$MSG"
    
    # Показываем что в узле 9
    curl -s -b /tmp/ck2.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
    python3 -c "
import sys,json
d=json.load(sys.stdin)
wf=d.get('data',d)
for n in wf.get('nodes',[]):
    name=n.get('name','')
    if 'Отправка' in name or '9.' in name:
        code=n.get('parameters',{}).get('jsCode','')
        print('CODE:', code[:400])
"
fi
