#!/usr/bin/env python3
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=10)
    except: pass

# Новый системный промпт для Claude — оценка новостей
NEW_SCORING_SYSTEM = (
    "Ты оцениваешь новости для Telegram канала агентства недвижимости Grandvest (Москва). "
    "Оцени релевантность новости по шкале 1-10. Отвечай ТОЛЬКО JSON: {\"score\": N, \"reason\": \"краткое объяснение\"}\n\n"
    
    "ОЦЕНКА 8-10 (высокий приоритет, публикуем обязательно):\n"
    "• Рынок недвижимости: офисы, склады, торговля, жильё, земля\n"
    "• Ставки аренды и продажи, вакантность, сделки, объёмы ввода\n"
    "• Ипотека: ставки, программы, условия, объёмы выдачи\n"
    "• Инвестиции в недвижимость, доходность, фонды, ЗПИФ\n"
    "• Строительство: девелоперы, проекты, разрешения, ввод объектов\n"
    "• Законодательство в сфере недвижимости и строительства:\n"
    "  - изменения в законах об аренде, ипотеке, долевом строительстве\n"
    "  - законы о градостроительстве, зонировании, генплан\n"
    "  - налоги на недвижимость, льготы, субсидии\n"
    "  - нормы СНиП, технические регламенты в строительстве\n"
    "  - решения Госдумы, Правительства, ЦБ по недвижимости\n"
    "• Крупные застройщики: ПИК, Самолёт, ЛСР, Эталон, ФСК\n"
    "• Московская агломерация, регионы России\n\n"
    
    "ОЦЕНКА 5-7 (средний приоритет, публикуем если нет лучшего):\n"
    "• Макроэкономика влияющая на рынок: ключевая ставка ЦБ, инфляция\n"
    "• Банковский сектор: кредиты бизнесу под залог недвижимости\n"
    "• Инфраструктура: метро, дороги, которые влияют на цены недвижимости\n"
    "• Бизнес-новости крупных арендаторов (открытие/закрытие офисов)\n\n"
    
    "ОЦЕНКА 1-4 (не публикуем):\n"
    "• Политика, спорт, развлечения без связи с недвижимостью\n"
    "• Международные новости без влияния на российский рынок\n"
    "• Реклама, опросы, конкурсы\n"
    "• Технологии, IT без связи со стройтехом или PropTech\n\n"
    
    "Отвечай ТОЛЬКО JSON без пояснений: {\"score\": N, \"reason\": \"1-2 слова\"}"
)

# Также обновляем user message для scoring
NEW_SCORING_USER = "={{ 'Оцени релевантность этой новости (1-10):\\n\\n' + ($input.first().json.text || $input.first().json.content || $input.first().json.message || $input.first().json.title || '') }}"

subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

fixes = []
for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue

    changed = False
    or_key = ''
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: or_key = keys[0]

    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})
        url = params.get('url','')

        # Claude — оценка поста (HTTP Request к OpenRouter)
        is_scoring = ('Claude' in name or 'оценк' in name.lower()) and \
                     ntype == 'n8n-nodes-base.httpRequest' and \
                     'openrouter' in url.lower()

        if is_scoring:
            jb = str(params.get('jsonBody','')).strip()
            clean = jb[1:].strip() if jb.startswith('=') else jb
            print(f"Found scoring node: {name!r} in {wf_name!r}")

            try:
                body = json.loads(clean) if clean else {}
                model = body.get('model','?')
                print(f"  model={model} max_tokens={body.get('max_tokens','?')}")

                # Обновляем системный промпт
                body['model'] = 'anthropic/claude-sonnet-4-5'
                body['max_tokens'] = 150
                for msg in body.get('messages',[]):
                    if msg.get('role') == 'system':
                        msg['content'] = NEW_SCORING_SYSTEM
                    if msg.get('role') == 'user':
                        msg['content'] = NEW_SCORING_USER

                params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                n['parameters'] = params
                changed = True
                fixes.append(f"[{wf_name}] '{name}': промпт оценки обновлён")
                print(f"  FIXED!")

            except Exception as e:
                print(f"  Error: {e}")
                if or_key:
                    new_body = {
                        "model": "anthropic/claude-sonnet-4-5",
                        "max_tokens": 150,
                        "messages": [
                            {"role": "system", "content": NEW_SCORING_SYSTEM},
                            {"role": "user", "content": NEW_SCORING_USER}
                        ]
                    }
                    params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': промпт пересоздан")
                    print(f"  REBUILT!")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(12):
    time.sleep(5)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

print(f"Fixes: {fixes}")
tg(
    '✅ <b>Шкала оценки обновлена</b>\n\n'
    '<b>🟢 8-10 (публикуем обязательно):</b>\n'
    '• Рынок недвижимости (офисы, склады, торговля, жильё)\n'
    '• Ставки аренды, продажи, вакантность, сделки\n'
    '• <b>Ипотека</b> — ставки, программы, объёмы\n'
    '• <b>Инвестиции</b> в недвижимость, ЗПИФ, доходность\n'
    '• <b>Строительство</b> — девелоперы, проекты, ввод\n'
    '• <b>Законодательство</b> в сфере недвижимости:\n'
    '  — законы об аренде, ипотеке, долевом строительстве\n'
    '  — градостроительство, зонирование, генплан\n'
    '  — налоги, льготы, субсидии на недвижимость\n'
    '  — решения Госдумы, Правительства, ЦБ\n\n'
    '<b>🟡 5-7 (публикуем если нет лучшего):</b>\n'
    '• Ключевая ставка ЦБ, инфляция, макроэкономика\n'
    '• Инфраструктура влияющая на цены\n\n'
    '<b>🔴 1-4 (не публикуем):</b>\n'
    '• Политика, спорт, IT без связи с недвижимостью\n\n'
    '🎯 Цель: 5-15 публикаций в рабочий день'
)
