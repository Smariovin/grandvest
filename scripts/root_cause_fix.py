#!/usr/bin/env python3
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
PAT = os.environ.get('GH_PAT','')

def tg(msg):
    if not BOT: print("TG:", msg[:200]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== ROOT CAUSE FIX ===")
fixes = []

subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Проверить структуру БД
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

for tbl in tables:
    if 'execut' in tbl.lower() or 'workflow' in tbl.lower():
        cur.execute("PRAGMA table_info(" + tbl + ")")
        cols = [r[1] for r in cur.fetchall()]
        print("Table " + tbl + ": " + str(cols))

cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
if not row:
    tg("ERROR: workflow not found!")
    conn.close()
    exit(1)

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
changed = False

print("Workflow: " + wf_name + ", nodes: " + str(len(nodes)))

# Новый правильный код для узла "1. Парсинг HTML Telegram"
NODE1_CODE = '''const items = $input.all();
const results = [];

for (const item of items) {
  const html = item.json.html || '';
  const channel = item.json.channel || '';
  const sourceUrl = item.json.source_url || '';
  
  // Извлекаем текст - убираем все HTML теги
  let text = html;
  
  // Убираем теги br и p с заменой на пробел
  text = text.replace(/<br\s*\/?>/gi, ' ');
  text = text.replace(/<\/p>|<p[^>]*>/gi, ' ');
  // Убираем ссылки - оставляем текст
  text = text.replace(/<a[^>]*>([^<]*)<\/a>/gi, '$1');
  // Убираем все остальные теги
  text = text.replace(/<[^>]+>/g, '');
  // Декодируем HTML entities
  text = text.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');
  text = text.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&nbsp;/g,' ');
  // Убираем лишние пробелы
  text = text.replace(/\s+/g,' ').trim();
  
  // Извлекаем дату публикации
  const timeMatch = html.match(/datetime="([^"]+)"/);
  const pubTime = timeMatch ? timeMatch[1] : new Date().toISOString();
  
  console.log('Channel: ' + channel + ' | Text length: ' + text.length);
  console.log('Text preview: ' + text.substring(0, 100));
  
  if (text && text.length >= 20) {
    results.push({
      json: {
        text: text,
        title: text.substring(0, 100),
        channel: channel,
        source_url: sourceUrl,
        pub_time: pubTime
      }
    });
  }
}

if (results.length === 0) {
  console.log('WARNING: no text extracted from HTML');
}

return results;'''

# Новый код для дедупликации
NODE2_CODE = '''const items = $input.all();
const staticData = $getWorkflowStaticData('global');
if (!staticData.publishedTitles) staticData.publishedTitles = [];
const published = staticData.publishedTitles;

const unique = [];
for (const item of items) {
  const text = item.json.text || item.json.title || '';
  if (!text || text.length < 10) continue;
  const key = text.substring(0, 60).toLowerCase().trim();
  const isDup = published.some(function(p) { return p.substring(0, 60).toLowerCase() === key; });
  if (!isDup) {
    unique.push(item);
  } else {
    console.log('Duplicate skipped: ' + key.substring(0, 40));
  }
}
console.log('Dedup: in=' + items.length + ' out=' + unique.length);
return unique;'''

# Новый правильный body для Claude оценки
CLAUDE_EVAL_BODY = {
    "model": "anthropic/claude-sonnet-4-5",
    "max_tokens": 100,
    "messages": [
        {
            "role": "system",
            "content": "You are a real estate news scorer. Score news 1-10 for Moscow commercial real estate relevance. Return ONLY JSON: {\"score\": 7, \"topic\": \"warehouse\"}"
        },
        {
            "role": "user",
            "content": "={{ $('1. Парсинг HTML Telegram').first().json.text }}"
        }
    ]
}

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    
    print("\nNode: " + name + " | " + ntype)
    
    if ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode','')
        print("  Code preview: " + code[:150])
        
        # Исправляем узел парсинга HTML
        if '1.' in name and ('Парсинг' in name or 'HTML' in name):
            print("  -> FIXING HTML parser node")
            params['jsCode'] = NODE1_CODE
            n['parameters'] = params
            changed = True
            fixes.append("Node 1: HTML parser fixed")
        
        # Исправляем дедупликацию
        elif '2.' in name and 'Дедуплик' in name:
            print("  -> FIXING dedup node")
            params['jsCode'] = NODE2_CODE
            n['parameters'] = params
            changed = True
            fixes.append("Node 2: dedup fixed")
        
        # Узел 9 - PAT
        elif '9.' in name or ('Отправка' in name and 'Telegram' in name):
            if PAT and ('github.com' in code or 'grandvest-publisher' in code):
                old_pats = re.findall('ghp_[A-Za-z0-9]{30,}', code)
                for op in old_pats:
                    if op != PAT:
                        code = code.replace(op, PAT)
                        params['jsCode'] = code
                        n['parameters'] = params
                        changed = True
                        fixes.append("Node 9: PAT updated")
    
    elif ntype == 'n8n-nodes-base.httpRequest':
        url_v = params.get('url','')
        bct = params.get('bodyContentType','?')
        jb = params.get('jsonBody','')
        print("  url=" + url_v[:60])
        print("  bct=" + str(bct) + " jsonBody=" + str(jb)[:200])
        
        # Claude оценка поста
        if 'openrouter' in url_v.lower() and 'оценк' in name.lower():
            print("  -> FIXING Claude eval node")
            params['bodyContentType'] = 'json'
            params['specifyBody'] = 'json'
            params['jsonBody'] = json.dumps(CLAUDE_EVAL_BODY, ensure_ascii=False)
            n['parameters'] = params
            changed = True
            fixes.append("Claude eval: body with correct text field")

if changed:
    cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
               (json.dumps(nodes, ensure_ascii=False), wf_id))
    print("\nSaved " + str(len(fixes)) + " fixes")

conn.commit()
conn.close()

# Рестарт
subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

# Сброс дедупликации
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)
time.sleep(2)

# Тест
print("Test webhook...")
test_html = (
    '<div class="tgme_widget_message_text js-message_text">'
    'Рынок складской недвижимости Москвы 2026: ставки аренды класса А выросли до 10 200 рублей за кв.м в год. '
    'Вакантность составила 0.8 процента — исторический минимум. '
    'Спрос формируют маркетплейсы Wildberries и Ozon.'
    '</div>'
    '<time datetime="2026-06-28T22:40:00+00:00">22:40</time>'
)
payload = json.dumps({'channel':'CRERussia','html':test_html}).encode('utf-8')
try:
    res = urllib.request.urlopen(
        urllib.request.Request('http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type':'application/json'}), timeout=60)
    print("Webhook: " + str(res.status))
    webhook_ok = True
except Exception as e:
    print("Webhook error: " + str(e))
    webhook_ok = False

time.sleep(20)

# Проверяем последний exec через n8n REST API
exec_info = "n/a"
try:
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    with opener.open("http://localhost:5678/rest/executions?limit=1&workflowId=F24jvKiXJIs4wRiZ",timeout=10) as r:
        ed = json.loads(r.read())
    execs = ed.get('data',{}).get('data', ed.get('data',[]))
    if isinstance(execs,list) and execs:
        ex = execs[0]
        exec_info = str(ex.get('status')) + " @ " + str(ex.get('startedAt',''))[:16]
        rd = ex.get('data',{}).get('resultData',{}).get('runData',{})
        lines = []
        for nn, nd in list(rd.items()):
            if nd and nd[0]:
                items_d = nd[0].get('data',{}).get('main',[[]])[0]
                has = bool(items_d and items_d[0])
                txt = ""
                if has:
                    s = items_d[0].get('json',{})
                    for f in ['text','tg_post','content','score','images']:
                        if f in s:
                            txt = str(s[f])[:50]
                            break
                lines.append(("OK " if has else "NO ") + nn + ": " + txt)
        exec_info += "\n" + "\n".join(lines[:15])
except Exception as e:
    exec_info = "API err: " + str(e)

tg(
    "<b>ROOT CAUSE FIX</b>\n\n"
    "<b>Что исправлено:</b>\n" + ("\n".join("• " + f for f in fixes) if fixes else "нет изменений") +
    "\n\n<b>Тест webhook:</b> " + ("OK" if webhook_ok else "FAIL") +
    "\n\n<b>Детали последнего exec:</b>\n" + exec_info[:1500]
)
print("DONE. fixes=" + str(fixes) + ", webhook=" + str(webhook_ok))
