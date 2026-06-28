#!/usr/bin/env python3
"""
Исправляем RSS workflow:
1. HTTP Request6: пересоздаём JSON body правильно
2. Code in JavaScript3 (дедупликация): убираем require('fs'), используем $getWorkflowStaticData
"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Дедупликация БЕЗ require('fs') — используем StaticData n8n
DEDUP_NO_FS = """const items = $input.all();
const staticData = $getWorkflowStaticData('global');
if (!staticData.published) staticData.published = [];

const unique = [];
for (const item of items) {
  const title = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 80);
  if (!title) continue;
  if (!staticData.published.includes(title)) {
    unique.push(item);
  }
}
// Ограничиваем размер кэша
if (staticData.published.length > 500) {
  staticData.published = staticData.published.slice(-300);
}
return unique.slice(0, 1);"""

# Запись в дедупликацию БЕЗ require('fs')
WRITE_DEDUP_NO_FS = """const item = $input.first().json;
const title = (item.title || item.text || '').trim().toLowerCase().substring(0, 80);
if (title) {
  const staticData = $getWorkflowStaticData('global');
  if (!staticData.published) staticData.published = [];
  if (!staticData.published.includes(title)) {
    staticData.published.push(title);
  }
}
return [$input.first()];"""

# Правильный промпт для генерации
PROMPT_SYSTEM = (
    "Ты - эксперт по рынку недвижимости России с 15-летним опытом. "
    "Пишешь посты для Telegram канала агентства Grandvest (Москва).\n\n"
    "Переписывай новость в формате экспертного поста, сохраняя суть оригинала.\n\n"
    "СТРУКТУРА:\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "[ФАКТЫ: 4-5 предложений с цифрами из новости]\n\n"
    "[КОНТЕКСТ: 3-4 предложения — связь с рынком недвижимости]\n\n"
    "[ВЛИЯНИЕ: 2-3 предложения для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения]\n\n"
    "💡 Практический совет: [2 предложения]\n\n"
    "👉 @Grandvest_bot\n\n"
    "ТРЕБОВАНИЯ: 1500-2000 символов. Только факты из новости."
)

USER_MSG_RSS = "={{ 'Перепиши новость:\\n\\nИсточник: ' + ($input.first().json.source || 'RSS') + '\\nЗаголовок: ' + ($input.first().json.title || '') + '\\n\\nТекст:\\n' + ($input.first().json.description || $input.first().json.content || $input.first().json.text || '') }}"

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
    
    is_rss = 'RSS' in wf_name or 'новост' in wf_name.lower() or 'сбор' in wf_name.lower()
    if not is_rss:
        continue
    
    print(f"\n=== {wf_name} ({wf_id}) ===")
    changed = False
    
    # Ищем OR ключ
    or_key = ''
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: or_key = keys[0]
    print(f"OR key: {or_key[:20]}...")
    
    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})
        url = params.get('url','')
        code = params.get('jsCode', params.get('code',''))
        
        # Исправляем Code узлы с require('fs')
        if 'code' in ntype.lower() and "require('fs')" in code:
            print(f"  Found fs node: {name!r}")
            # Определяем тип узла
            if 'published' in code and 'push' in code:
                # Это запись в дедупликацию
                n['parameters']['jsCode'] = WRITE_DEDUP_NO_FS
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] '{name}': fs→StaticData (write)")
                print(f"  FIXED write dedup!")
            else:
                # Это чтение дедупликации
                n['parameters']['jsCode'] = DEDUP_NO_FS
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] '{name}': fs→StaticData (read)")
                print(f"  FIXED read dedup!")
        
        # Исправляем HTTP Request6 — OpenRouter
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            print(f"  Found OR node: {name!r}")
            
            new_body = {
                "model": "anthropic/claude-sonnet-4-5",
                "max_tokens": 3000,
                "messages": [
                    {"role": "system", "content": PROMPT_SYSTEM},
                    {"role": "user", "content": USER_MSG_RSS}
                ]
            }
            
            # Записываем как jsonBody (не rawBody!)
            params['specifyBody'] = 'json'
            params['bodyContentType'] = 'json'
            params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
            params.pop('rawBody', None)
            params.pop('body', None)
            n['parameters'] = params
            changed = True
            fixes.append(f"[{wf_name}] '{name}': JSON body rebuilt, claude-sonnet-4-5")
            print(f"  FIXED HTTP Request6!")
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))
        print(f"  Saved!")

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

print(f"\nFixes: {fixes}")
msg = "✅ <b>RSS Fix:</b>\n" + '\n'.join(f"• {f}" for f in fixes) if fixes else "⚠️ RSS: ничего не исправлено"
tg(msg)
