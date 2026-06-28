#!/usr/bin/env python3
import sqlite3, json, re, subprocess, time, urllib.request, urllib.parse, os

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

PROMPT = (
    "Ты - эксперт по рынку недвижимости России с 15-летним опытом. "
    "Пишешь посты для Telegram канала агентства Grandvest (Москва).\n\n"
    "Переписывай новость в формате экспертного поста, сохраняя суть оригинала.\n\n"
    "СТРУКТУРА:\n"
    "🏢 [ЗАГОЛОВОК — точно отражает суть новости, 8-12 слов]\n\n"
    "[ФАКТЫ: 4-5 предложений с цифрами и датами из новости]\n\n"
    "[КОНТЕКСТ: 3-4 предложения — связь с рынком недвижимости]\n\n"
    "[ВЛИЯНИЕ: 2-3 предложения для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения]\n\n"
    "💡 Практический совет: [2 предложения]\n\n"
    "👉 @Grandvest_bot\n\n"
    "ТРЕБОВАНИЯ: 1500-2000 символов. Только факты из новости."
)

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
    is_rss = 'RSS' in wf_name or 'новост' in wf_name.lower() or 'сбор' in wf_name.lower()
    
    # OR ключ
    or_key = ''
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: or_key = keys[0]
    
    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})
        url = params.get('url','')
        
        if ntype != 'n8n-nodes-base.httpRequest': continue
        if 'openrouter' not in url.lower(): continue
        
        print(f"\n[{wf_name}] {name!r}")
        
        # Определяем user content
        if is_rss:
            user_content = (
                "={{ 'Перепиши эту новость в формате экспертного поста:\\n\\n"
                "Источник: ' + ($input.first().json.source || 'RSS') + '\\n"
                "Ссылка: ' + ($input.first().json.link || '') + '\\n\\n"
                "Заголовок: ' + ($input.first().json.title || '') + '\\n\\n"
                "Текст:\\n' + ($input.first().json.description || $input.first().json.content || $input.first().json.text || '') }}"
            )
        else:
            user_content = (
                "={{ 'Перепиши эту новость в формате экспертного поста:\\n\\n"
                "Источник: ' + ($input.first().json.source || $input.first().json.channel || 'Telegram') + '\\n\\n"
                "Текст новости:\\n' + ($input.first().json.text || $input.first().json.content || $input.first().json.message || '') }}"
            )
        
        new_body = {
            "model": "anthropic/claude-sonnet-4-5",
            "max_tokens": 3000,
            "messages": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": user_content}
            ]
        }
        
        params['specifyBody'] = 'json'
        params['bodyContentType'] = 'json'
        params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
        params.pop('rawBody', None)
        params.pop('body', None)
        n['parameters'] = params
        changed = True
        fixes.append(f"[{wf_name}] {name!r}: Fixed!")
        print(f"  ✅ FIXED")
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
print("n8n started")

for _ in range(12):
    time.sleep(5)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

print(f"Fixes: {fixes}")
tg("✅ <b>RSS SQLite Fix:</b>\n" + '\n'.join(f"• {f}" for f in fixes) if fixes else "⚠️ Нет изменений")
