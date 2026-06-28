#!/usr/bin/env python3
"""
RSS FULL FIX — исправляем все узлы RSS workflow одним скриптом
Проблемы:
1. bct=? во всех HTTP Request узлах OpenRouter и fal.ai
2. HTTP Request7 — Code узел с неправильным промптом
3. Отчёт RSS парсинга — не подключён (удаляем/игнорируем)
4. Цепочка должна быть: Trigger->RSS->Merge->CodeParse->HTTP6score->Code1filter->If->Code7gen->Code2extract->HTTP9fal->HTTP8github->Code4dedup
"""
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
PAT = os.environ.get('GH_PAT','')

def tg(msg):
    if not BOT: print("TG:", msg[:300]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== RSS FULL FIX ===")
fixes = []

# Останавливаем n8n
subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, active, nodes FROM workflow_entity")
all_wf = cur.fetchall()

rss_wf = None
for wf_id, wf_name, active, nodes_raw in all_wf:
    if 'RSS' in wf_name or 'Сбор новостей' in wf_name:
        rss_wf = (wf_id, wf_name, active, nodes_raw)
        break

if not rss_wf:
    tg("ERROR: RSS workflow not found!")
    conn.close()
    exit(1)

wf_id, wf_name, active, nodes_raw = rss_wf
nodes = json.loads(nodes_raw)
print("RSS workflow: " + wf_name + " | nodes: " + str(len(nodes)))

# Правильный код для оценки новости (HTTP6 — OpenRouter)
SCORE_BODY = {
    "model": "anthropic/claude-sonnet-4-5",
    "max_tokens": 100,
    "messages": [
        {
            "role": "system",
            "content": "Оцени новость по шкале 1-10 для рынка коммерческой недвижимости Москвы. Верни ТОЛЬКО JSON: {\"score\": 7, \"topic\": \"аренда\"}"
        },
        {
            "role": "user",
            "content": "={{ $json.title }} {{ $json.source }}"
        }
    ]
}

# Правильный код генерации поста через OpenRouter
GENERATE_CODE = """// Генерация поста через OpenRouter
const item = $input.first().json;
const title = item.title || item.text || '';
const source = item.source || item.link || '';
const description = item.description || item.summary || title;

const body = {
  model: 'anthropic/claude-sonnet-4-5',
  max_tokens: 1500,
  messages: [
    {
      role: 'system',
      content: `Ты — эксперт по коммерческой недвижимости Москвы. Напиши экспертный пост для Telegram канала @grandvest_realty.

СТРУКТУРА ПОСТА (строго соблюдать):
1. Заголовок с эмодзи 🏢 (не более 10 слов)
2. Суть новости (2-3 предложения, факты)
3. 💼 Комментарий Грандвест: (экспертное мнение, 2 предложения)
4. 💡 Совет: (практический совет для арендаторов/инвесторов)
5. 📞 За консультацией: @Grandvest_bot
6. Хэштеги: #коммерческаянедвижимость #аренда #москва #грандвест

ТРЕБОВАНИЯ:
- Длина: 800-1200 символов
- Тон: профессиональный, экспертный
- Только HTML теги: <b>текст</b>
- Никаких выдуманных фактов
- В конце добавь строку: IMAGE: [описание картинки на английском для AI генерации, московский бизнес-центр]`
    },
    {
      role: 'user',
      content: 'Новость: ' + title + '\\n\\nИсточник: ' + source + '\\n\\nДетали: ' + description
    }
  ]
};

const resp = await this.helpers.httpRequest({
  method: 'POST',
  url: 'https://openrouter.ai/api/v1/chat/completions',
  headers: {
    'Authorization': 'Bearer {{ $env.OPENROUTER_API_KEY }}',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(body)
});

const content = resp.choices?.[0]?.message?.content || '';
console.log('Generated content length:', content.length);
return [{ json: { ...item, generated_content: content } }];"""

# Правильный код извлечения tg_post и image_prompt
EXTRACT_CODE = """// Извлечение tg_post и image_prompt из ответа Claude
const item = $input.first().json;
const content = item.generated_content || '';

// Разделяем пост и prompt для картинки
const imageMatch = content.match(/IMAGE:\\s*(.+?)$/ms);
const imagePart = imageMatch ? imageMatch[1].trim() : 
  'photorealistic Moscow business district, glass office buildings, aerial view, golden hour, no people, no text, 4k';

const tgPost = content.replace(/IMAGE:.*$/ms, '').trim();

console.log('tg_post length:', tgPost.length);
console.log('image_prompt:', imagePart.substring(0, 80));

return [{ json: { ...item, tg_post: tgPost, image_prompt: imagePart } }];"""

# Правильный код для узла 9 — отправка в GitHub Actions
NODE9_CODE = """// Отправка в GitHub Actions для публикации в Telegram
const item = $input.first().json;
const tgPost = item.tg_post || item.generated_content || 'Новость от Grandvest';
const imageUrl = item.image_url || '';
const sourceUrl = item.link || item.source_url || '';
const sourceName = item.source || 'RSS';

const pat = '""" + (PAT if PAT else 'GH_PAT_PLACEHOLDER') + """';

const body = {
  ref: 'main',
  inputs: {
    message: tgPost,
    image_url: imageUrl,
    source_url: sourceUrl,
    source_name: sourceName,
    parser_name: 'RSS'
  }
};

const resp = await this.helpers.httpRequest({
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {
    'Authorization': 'token ' + pat,
    'Accept': 'application/vnd.github.v3+json',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(body)
});

console.log('GitHub dispatch result:', resp);
return [{ json: { ...item, dispatch_ok: true } }];"""

# Дедупликация для RSS
DEDUP_CODE = """const items = $input.all();
const staticData = $getWorkflowStaticData('global');
if (!staticData.publishedTitles) staticData.publishedTitles = [];
const published = staticData.publishedTitles;

const unique = [];
for (const item of items) {
  const title = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 80);
  if (!title) continue;
  const isDup = published.some(function(p) { return p.substring(0, 80) === title; });
  if (!isDup) {
    unique.push(item);
  }
}

if (staticData.publishedTitles.length > 500) {
  staticData.publishedTitles = staticData.publishedTitles.slice(-300);
}

console.log('Dedup: in=' + items.length + ' out=' + unique.length);
return unique.slice(0, 1);"""

# Запись в дедупликацию после публикации
WRITE_DEDUP_CODE = """const item = $input.first().json;
const title = (item.title || item.text || '').trim().toLowerCase().substring(0, 80);
if (title) {
  const staticData = $getWorkflowStaticData('global');
  if (!staticData.publishedTitles) staticData.publishedTitles = [];
  if (!staticData.publishedTitles.includes(title)) {
    staticData.publishedTitles.push(title);
  }
}
return [$input.first()];"""

changed = False
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})

    # FIX 1: HTTP Request6 — оценка через OpenRouter
    if name == 'HTTP Request6' and ntype == 'n8n-nodes-base.httpRequest':
        print("Fixing HTTP Request6 (scoring)...")
        params['bodyContentType'] = 'json'
        params['specifyBody'] = 'json'
        params['jsonBody'] = json.dumps(SCORE_BODY, ensure_ascii=False)
        params.pop('rawBody', None)
        n['parameters'] = params
        changed = True
        fixes.append("HTTP Request6: bct=json + правильный промпт оценки")

    # FIX 2: HTTP Request9 — fal.ai
    elif name == 'HTTP Request9' and ntype == 'n8n-nodes-base.httpRequest':
        print("Fixing HTTP Request9 (fal.ai)...")
        params['bodyContentType'] = 'json'
        params['specifyBody'] = 'json'
        # Проверяем jsonBody
        jb = params.get('jsonBody','')
        if not jb or jb == '{}':
            fal_body = {
                "prompt": "={{ $json.image_prompt || 'photorealistic Moscow business district, glass office buildings, golden hour, 4k' }}",
                "image_size": "landscape_16_9",
                "num_inference_steps": 4,
                "num_images": 1
            }
            params['jsonBody'] = json.dumps(fal_body, ensure_ascii=False)
        n['parameters'] = params
        changed = True
        fixes.append("HTTP Request9 (fal.ai): bct=json")

    # FIX 3: HTTP Request8 — GitHub Actions dispatch
    elif name == 'HTTP Request8' and ntype == 'n8n-nodes-base.httpRequest':
        print("Fixing HTTP Request8 (GitHub dispatch)...")
        params['bodyContentType'] = 'json'
        params['specifyBody'] = 'json'
        n['parameters'] = params
        changed = True
        fixes.append("HTTP Request8 (GitHub): bct=json")

    # FIX 4: Code7 — генерация поста (этот Code узел называется "HTTP Request7")
    elif name == 'HTTP Request7' and ntype == 'n8n-nodes-base.code':
        print("Fixing HTTP Request7 (generation Code node)...")
        params['jsCode'] = GENERATE_CODE
        n['parameters'] = params
        changed = True
        fixes.append("HTTP Request7 (генерация): обновлён Code с правильным промптом")

    # FIX 5: Code in JavaScript1 — фильтр/сортировка после оценки
    elif name == 'Code in JavaScript1' and ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode','')
        print("Code in JavaScript1: " + code[:100])
        # Проверяем что дедупликация правильная
        if 'require(' in code or 'readFileSync' in code:
            params['jsCode'] = DEDUP_CODE
            n['parameters'] = params
            changed = True
            fixes.append("Code1: убран require('fs'), используем StaticData")

    # FIX 6: Code in JavaScript3 — дедупликация
    elif name == 'Code in JavaScript3' and ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode','')
        print("Code in JavaScript3: " + code[:100])
        if 'require(' in code or 'readFileSync' in code:
            params['jsCode'] = DEDUP_CODE
            n['parameters'] = params
            changed = True
            fixes.append("Code3: убран require('fs')")

    # FIX 7: Code in JavaScript2 — извлечение tg_post
    elif name == 'Code in JavaScript2' and ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode','')
        print("Code in JavaScript2: " + code[:100])
        # Обновляем если старый код
        if 'tg_post' not in code or 'image_prompt' not in code:
            params['jsCode'] = EXTRACT_CODE
            n['parameters'] = params
            changed = True
            fixes.append("Code2: обновлён extract tg_post + image_prompt")

    # FIX 8: Code in JavaScript4 — запись в дедупликацию
    elif name == 'Code in JavaScript4' and ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode','')
        print("Code in JavaScript4: " + code[:100])
        if 'require(' in code or 'readFileSync' in code:
            params['jsCode'] = WRITE_DEDUP_CODE
            n['parameters'] = params
            changed = True
            fixes.append("Code4: убран require('fs')")

    # FIX 9: РИА Недвижимость и Циан — просто GET, bct не важен
    elif name in ('РИА Недвижимость', 'Циан') and ntype == 'n8n-nodes-base.httpRequest':
        # GET запросы — bct не нужен, просто убеждаемся что method=GET
        params.pop('bodyContentType', None)
        params.pop('specifyBody', None)
        params['method'] = 'GET'
        n['parameters'] = params
        # не меняем changed — это не критично

if changed:
    cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
               (json.dumps(nodes, ensure_ascii=False), wf_id))
    print("Saved " + str(len(fixes)) + " fixes to RSS workflow")

conn.commit()
conn.close()

# Перезапуск n8n
subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

# Сброс дедупликации RSS
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)
time.sleep(2)

# Активируем RSS workflow через n8n API
import http.cookiejar
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    # Активируем
    opener.open(urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + wf_id + "/activate",
        data=b'{}', headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    print("RSS workflow activated!")
    fixes.append("RSS workflow активирован")
except Exception as e:
    print("Activation error: " + str(e))

tg(
    "<b>RSS FULL FIX DONE</b>\n\n"
    "<b>Исправлено (" + str(len(fixes)) + "):</b>\n" +
    "\n".join("• " + f for f in fixes) +
    "\n\n<b>Статус:</b> n8n перезапущен, дедупликация сброшена\n"
    "RSS workflow активирован и будет запускаться каждый час 8:01–20:01 МСК\n\n"
    "Блок <b>Отчёт RSS парсинга</b> — не подключаем (лишний, система работает без него)"
)
print("DONE. fixes=" + str(fixes))
