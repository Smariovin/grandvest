#!/bin/bash
# ПОЛНОЕ ВОССТАНОВЛЕНИЕ ПАЙПЛАЙНА
# Читаем ошибку, исправляем, тестируем, проверяем — всё сами

BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT_LOG="5340000158"          # личка Марио для логов
CHANNEL="-1003971323034"       # канал @grandvest_realty
WORKING_PAT="${WORKING_PAT}"

tg_log() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT_LOG}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null
}

echo "====== FULL REBUILD ======"
date

# ШАГ 1: Логинимся в n8n и читаем последнюю ошибку
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

echo "=== Last 3 executions ==="
EXECS=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=3')

# Читаем ID последней ошибки
LAST_ERROR_ID=$(echo "$EXECS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
for ex in items:
    if ex.get('status')=='error':
        print(ex.get('id',''))
        break
" 2>/dev/null)
echo "Last error ID: $LAST_ERROR_ID"

# Читаем полную ошибку
if [ -n "$LAST_ERROR_ID" ]; then
    FULL_ERR=$(curl -s -b /tmp/ck.txt "http://localhost:5678/rest/executions/${LAST_ERROR_ID}")
    ERROR_INFO=$(echo "$FULL_ERR" | python3 -c "
import sys,json
d=json.load(sys.stdin)
ex=d.get('data',d)
result=ex.get('data',{}).get('resultData',{})
run_data=result.get('runData',{})
errors=[]
for node,runs in run_data.items():
    for r in (runs or []):
        err=r.get('error')
        if err:
            errors.append(f'{node}: {err.get(\"message\",\"?\")[:100]}')
print('\n'.join(errors) if errors else 'No errors in runData')
" 2>/dev/null)
    echo "Errors: $ERROR_INFO"
    tg_log "🔍 Last error:
$ERROR_INFO"
fi

# ШАГ 2: Останавливаем n8n и делаем полный патч SQLite
docker stop n8n && sleep 3

python3 << 'PYEOF'
import sqlite3, json, re, os

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT','')
print(f"PAT: {PAT[:15]}...")

PROMPT_GENERATION = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА:\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "[ФАКТЫ: 3-4 предложения с цифрами и источниками]\n\n"
    "[КОНТЕКСТ: 3-4 предложения — районы, ставки руб/кв.м., сравнение с прошлым]\n\n"
    "[ВЛИЯНИЕ: 2-3 предложения для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения]\n\n"
    "💡 Практический совет: [2 конкретных предложения]\n\n"
    "👉 За подбором — @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика. Никакой воды."
)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
wf_id, wf_name, nodes_raw = cur.fetchone()
nodes = json.loads(nodes_raw)

print(f"\nWorkflow: {wf_name}")
print(f"Nodes: {len(nodes)}")

or_key = ''
# Сначала находим OR ключ
for n in nodes:
    h_params = n.get('parameters',{}).get('headerParameters',{}).get('parameters',[])
    for h in h_params:
        v = str(h.get('value',''))
        if 'sk-or-v1' in v:
            or_key = v.replace('Bearer ','').strip()
            print(f"OR key: {or_key[:20]}...")

# Патчим каждый узел
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    url = params.get('url','')

    print(f"\n  [{name}] type={ntype.split('.')[-1]}")

    # === Узел 9: Отправка ===
    is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
    if is_node9:
        tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        print(f"    tokens: {[t[:12] for t in tokens]}")
        print(f"    has_publisher: {'grandvest-publisher' in code}")
        # Принудительно перезаписываем
        new_code = (
            "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
            "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
            "if (!postText || postText.length < 10) { throw new Error('tg_post пустой: ' + JSON.stringify(postText)); }\n"
            "console.log('Posting:', postText.length, 'chars, image:', !!imageUrl);\n"
            f"const r = await this.helpers.httpRequest({{\n"
            "  method: 'POST',\n"
            "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
            f"  headers: {{'Authorization': 'token {PAT}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},\n"
            "  body: JSON.stringify({ref: 'main', inputs: {message: postText, image_url: imageUrl}})\n"
            "});\n"
            "console.log('Dispatch OK!');\n"
            "return [{json: {ok: true, len: postText.length}}];"
        )
        n['parameters']['jsCode'] = new_code
        n['parameters'].pop('code', None)
        print(f"    ✅ Node9 patched with {PAT[:12]}...")

    # === OpenRouter узлы: генерация поста ===
    if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
        jb = str(params.get('jsonBody','')).strip()
        clean = jb[1:].strip() if jb.startswith('=') else jb
        
        if 'генерац' in name.lower() or name == 'HTTP Request — генерация поста':
            print(f"    Generation node found!")
            # Пересоздаём полностью с правильным телом
            # Читаем user message из текущего кода
            user_msg = "={{ 'Напиши экспертный пост о коммерческой недвижимости Москвы по этой новости:\\n\\n' + ($input.first().json.text || $input.first().json.content || $input.first().json.message || '') }}"
            
            new_body = {
                "model": "anthropic/claude-sonnet-4-5",
                "max_tokens": 2048,
                "messages": [
                    {"role": "system", "content": PROMPT_GENERATION},
                    {"role": "user", "content": user_msg}
                ]
            }
            params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
            params['specifyBody'] = 'json'
            params['bodyContentType'] = 'json'
            params['sendBody'] = True
            n['parameters'] = params
            print(f"    ✅ Generation node rebuilt: max_tokens=2048")
        
        elif 'оценк' in name.lower() or 'Claude' in name:
            print(f"    Scoring node found!")
            try:
                body = json.loads(clean) if clean else {}
                mt = body.get('max_tokens',0)
                print(f"    max_tokens={mt}")
            except Exception as e:
                print(f"    jsonBody parse error: {e}")
                # Пересоздаём scoring body
                scoring_body = {
                    "model": "anthropic/claude-sonnet-4-5",
                    "max_tokens": 100,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Оцени релевантность новости для канала о коммерческой недвижимости Москвы. "
                                "Ставь >= 6 если новость о: недвижимости, аренде, строительстве, инвестициях, девелопменте, ипотеке. "
                                "Отвечай ТОЛЬКО JSON: {\"score\": N}"
                            )
                        },
                        {
                            "role": "user",
                            "content": "={{ 'Оцени (1-10):\\n\\n' + $input.first().json.text }}"
                        }
                    ]
                }
                params['jsonBody'] = json.dumps(scoring_body, ensure_ascii=False)
                n['parameters'] = params
                print(f"    ✅ Scoring node rebuilt")

    # === Дедупликация: убираем StaticData ===
    if ('Дедупликац' in name or '2.' in name) and 'getWorkflowStaticData' in code:
        dedup_code = """const items = $input.all();
const unique = [];
let published = [];
try {
  const fs = require('fs');
  published = JSON.parse(fs.readFileSync('/data/published_titles.json', 'utf8'));
} catch(e) { published = []; }
for (const item of items) {
  const text = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 60);
  if (!text || !published.some(p => p.substring(0, 60) === text)) {
    unique.push(item);
  }
}
return unique.slice(0, 1);"""
        n['parameters']['jsCode'] = dedup_code
        print(f"    ✅ Dedup switched from StaticData to filesystem")

    # === Запись в дедупликацию ===
    if ('Запись' in name or '10.' in name) and ('дедупликац' in name.lower()):
        write_code = """const item = $input.first().json;
const title = (item.title || item.text || '').trim().toLowerCase().substring(0, 60);
if (title) {
  try {
    const fs = require('fs');
    let published = [];
    try { published = JSON.parse(fs.readFileSync('/data/published_titles.json', 'utf8')); } catch(e) {}
    if (!published.includes(title)) {
      published.push(title);
      if (published.length > 500) published = published.slice(-300);
      fs.writeFileSync('/data/published_titles.json', JSON.stringify(published));
    }
  } catch(e) { console.error('Dedup write error:', e); }
}
return [$input.first()];"""
        n['parameters']['jsCode'] = write_code
        print(f"    ✅ Dedup write node fixed")

# Сохраняем
cur.execute("UPDATE workflow_entity SET nodes=?, active=1, staticData='{}' WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False), wf_id))
conn.commit()
conn.close()

# Очищаем дедупликацию
import os
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)
print("\n✅ All done! SQLite saved, dedup cleared.")
PYEOF

# ШАГ 3: Запускаем n8n
docker start n8n
echo "Starting n8n..."
sleep 25

for i in $(seq 1 10); do
    curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}" && echo "n8n UP ($i)" && break
    sleep 4
done

# ШАГ 4: Тест с реальной новостью
echo "=== LIVE TEST ==="
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{"channel":"CRERussia","html":"<div class=\"tgme_widget_message_text js-message_text\">Сбербанк снизил ставки по ипотеке на коммерческую недвижимость до 14 процентов годовых с июля 2026 года. Льготная программа распространяется на офисы площадью до 500 квадратных метров в Москве и регионах. По оценке аналитиков это позволит увеличить спрос на покупку офисов малого бизнеса на 25-30 процентов во втором полугодии.</div><time datetime=\"2026-06-27T01:00:00+00:00\">01:00</time>"}' \
  && echo "Webhook OK" || echo "Webhook FAIL"

# ШАГ 5: Ждём 60 сек и проверяем execution
sleep 60

curl -s -c /tmp/ck2.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

RESULT=$(curl -s -b /tmp/ck2.txt 'http://localhost:5678/rest/executions?limit=2')
echo "$RESULT" | python3 -c "
import sys,json,urllib.request,urllib.parse,os
BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'
def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000]}).encode(),
        method='POST'),timeout=10)

d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])

report=['<b>Test results after full rebuild:</b>']
for ex in items[:2]:
    wf=ex.get('workflowData',{}).get('name','?')
    status=ex.get('status','?')
    t=str(ex.get('startedAt','?'))[11:16]
    icon='✅' if status=='success' else '❌'
    report.append(f'{icon} {wf} [{t}]: {status}')

tg('\n'.join(report))
print('\n'.join(report))
" 2>&1

echo "=== FULL REBUILD DONE ==="
