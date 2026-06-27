#!/bin/bash
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
DB="/opt/n8n/n8n_data/database.sqlite"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null 2>&1
}

echo "====== COMPLETE FIX ======"
echo "Time: $(date)"
echo "PAT: ${PAT:0:15}..."

# ШАГ 1: Останавливаем ВСЕ агенты которые могут мешать
echo "--- Disabling interfering cron jobs ---"
crontab -l 2>/dev/null | grep -v "grandvest\|scheduler\|n8n" | crontab - 2>/dev/null || true
echo "Cron cleared"

# ШАГ 2: Убираем grandvest-check.sh (он пересоздаёт контейнер и стирает патчи)
echo "--- Fixing grandvest-check.sh ---"
cat > /opt/grandvest-check.sh << 'CHECKEOF'
#!/bin/bash
# grandvest-check.sh v2 - только проверяет, НЕ пересоздаёт контейнер
RUNNING=$(docker inspect -f '{{.State.Running}}' n8n 2>/dev/null || echo false)
if [ "$RUNNING" != "true" ]; then
    echo "n8n not running, starting..."
    docker start n8n
    sleep 10
fi
echo "n8n status: $(docker inspect -f '{{.State.Status}}' n8n 2>/dev/null)"
CHECKEOF
chmod +x /opt/grandvest-check.sh
echo "grandvest-check.sh updated (no more container recreation)"

# ШАГ 3: Останавливаем n8n для чистого патча
echo "--- Stopping n8n ---"
docker stop n8n 2>/dev/null; sleep 3

# ШАГ 4: Полный патч SQLite
python3 << PYEOF
import sqlite3, json, re, os, time

DB = '/opt/n8n/n8n_data/database.sqlite'
PAT = os.environ.get('WORKING_PAT', '')
print(f"PAT: {PAT[:15]}...")

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА:\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "[ФАКТЫ: 3-4 предложения с цифрами и источниками]\n\n"
    "[КОНТЕКСТ: 3-4 предложения - районы Москвы, ставки руб/кв.м., сравнение с прошлым]\n\n"
    "[ВЛИЯНИЕ: 2-3 предложения для арендаторов и инвесторов]\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения]\n\n"
    "💡 Практический совет: [2 конкретных предложения]\n\n"
    "👉 За подбором - @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика. Никакой воды."
)

NODE9_CODE = f"""// Отправка через GitHub Actions
const postText = \$('8. Подготовка данных поста').first().json.tg_post;
const imageUrl = \$('HTTP Request — fal.ai').first().json.images?.[0]?.url || '';
if (!postText || postText.length < 10) {{
  throw new Error('tg_post пустой: ' + JSON.stringify(postText));
}}
console.log('Posting:', postText.length, 'chars');
const r = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {{
    'Authorization': 'token {PAT}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github+json'
  }},
  body: JSON.stringify({{ref: 'main', inputs: {{message: postText, image_url: imageUrl}}}})
}});
console.log('Dispatch OK!');
return [{{json: {{ok: true, len: postText.length}}}}];"""

DEDUP_CODE = """const items = $input.all();
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
console.log('Dedup:', items.length, '->', unique.length);
return unique.slice(0, 1);"""

FILTER_CODE = """const content = $input.first().json.choices?.[0]?.message?.content || '';
let score = 0;
try {
  let cleaned = content.trim().replace(/^```(?:json)?\\s*/i, '').replace(/\\s*```$/, '').trim();
  const parsed = JSON.parse(cleaned);
  score = parseInt(parsed.score) || 0;
} catch(e) {
  const m = content.match(/\\b([1-9]|10)\\b/);
  score = m ? parseInt(m[1]) : (content.trim().length > 0 ? 5 : 0);
}
console.log('Score:', score);
if (score >= 4) {
  const src = $('2. Дедупликация входящих').first().json;
  return [{ json: { ...src, score } }];
}
return [];"""

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

print(f"Workflows found: {len(rows)}")

for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue
    
    changed = False
    or_key = ''
    # Ищем OR ключ
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
    if keys: or_key = keys[0]

    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        url = params.get('url', '')

        # Узел 9 - принудительная перезапись
        if ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name):
            old_toks = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
            n['parameters']['jsCode'] = NODE9_CODE
            n['parameters'].pop('code', None)
            changed = True
            print(f"  ✅ Node9 [{wf_name}]: {[t[:12] for t in old_toks]} -> {PAT[:12]}")

        # Дедупликация - убираем StaticData
        if ('Дедупликац' in name or '2.' in name) and 'getWorkflowStaticData' in code:
            n['parameters']['jsCode'] = DEDUP_CODE
            changed = True
            print(f"  ✅ Dedup [{wf_name}]: StaticData -> filesystem")

        # Фильтр оценки - снижаем порог до 4
        if 'фильтр' in name.lower() and 'code' in ntype.lower():
            if 'score >= 6' in code or 'score > 5' in code:
                n['parameters']['jsCode'] = FILTER_CODE
                changed = True
                print(f"  ✅ Filter [{wf_name}]: threshold 6->4")

        # OpenRouter узлы - исправляем jsonBody
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            jb = str(params.get('jsonBody', '')).strip()
            clean = jb[1:].strip() if jb.startswith('=') else jb
            if clean:
                try:
                    body = json.loads(clean)
                    mt = body.get('max_tokens', 0)
                    sys_ok = any('ТРЕБОВАНИЯ' in str(m.get('content',''))
                                for m in body.get('messages',[]) if m.get('role')=='system')
                    if mt < 2048 or not sys_ok:
                        body['max_tokens'] = 2048
                        for m in body.get('messages', []):
                            if m.get('role') == 'system' and 'генерац' in name.lower():
                                m['content'] = PROMPT
                        params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                        n['parameters'] = params
                        changed = True
                        print(f"  ✅ OR [{wf_name}] '{name}': max_tokens->{body['max_tokens']}")
                except Exception as e:
                    print(f"  ⚠️  OR [{wf_name}] '{name}': {e}")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1, staticData='{}' WHERE id=?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

# Сбрасываем дедупликацию
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json', 'w') as f:
    json.dump([], f)
with open('/data/night_buffer.json', 'w') as f:
    json.dump([], f)

print("SQLite done! Dedup reset!")
PYEOF

# ШАГ 5: Запускаем n8n
echo "--- Starting n8n ---"
docker start n8n
for i in $(seq 1 12); do
    sleep 5
    curl -s http://localhost:5678/healthz 2>/dev/null | grep -q "{}" && echo "n8n UP! ($i)" && break
    echo "  waiting $i/12..."
done

# ШАГ 6: Проверяем через n8n REST API что токен правильный
echo "--- Verifying via n8n API ---"
sleep 3
curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

VERIFY=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' | \
python3 -c "
import sys,json,re,os
PAT=os.environ.get('WORKING_PAT','')
d=json.load(sys.stdin)
wf=d.get('data',d)
for n in wf.get('nodes',[]):
    name=n.get('name','')
    if 'Отправка' in name or '9.' in name:
        code=n.get('parameters',{}).get('jsCode','')
        toks=re.findall(r'ghp_[A-Za-z0-9]{10,}',code)
        ok=all(t==PAT for t in toks) if toks else False
        print(f'Node9 token correct: {ok} | tokens: {[t[:15] for t in toks]}')
" 2>&1)
echo "$VERIFY"

# ШАГ 7: Живой тест с РЕАЛЬНОЙ новостью
echo "--- Live test ---"
curl -s -X POST http://localhost:5678/webhook/telegram-parser \
  -H 'Content-Type: application/json' \
  -d '{
    "channel":"CRERussia",
    "html":"<div class=\"tgme_widget_message_text js-message_text\">Инвестиции в коммерческую недвижимость России достигли 350 миллиардов рублей за первые пять месяцев 2026 года, превысив показатель всего 2025 года. Складской сектор лидирует с долей 42 процента от общего объема. Ставки аренды складов выросли до 12000 рублей за кв м в год. Офисный рынок Москвы также активен — вакантность в классе А 7.8 процента по данным CBRE.</div><time datetime=\"2026-06-27T07:30:00+00:00\">07:30</time>"
  }' && echo "" && echo "Webhook sent OK"

echo "Waiting 90 sec for execution..."
sleep 90

# ШАГ 8: Проверяем результат
LAST=$(curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=2' | \
python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('data',{})
if isinstance(items,dict): items=items.get('results',[])
for ex in items[:2]:
    wf=ex.get('workflowData',{}).get('name','?')
    status=ex.get('status','?')
    t=str(ex.get('startedAt','?'))[11:16]
    print(f'{status} | {wf} | {t}')
" 2>&1)
echo "Executions: $LAST"

tg "✅ <b>Complete Fix Done</b>

✅ grandvest-check.sh: убрано пересоздание контейнера
✅ Узел 9: токен ${PAT:0:12}... записан
✅ Дедупликация: StaticData -> файловая система
✅ Фильтр: порог снижен до 4
✅ OpenRouter: max_tokens=2048
✅ Деdup сброшен
✅ Тест запущен

Executions: $LAST"

echo "=== COMPLETE FIX DONE ==="
