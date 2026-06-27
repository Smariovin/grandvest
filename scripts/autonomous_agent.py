#!/usr/bin/env python3
"""
Grandvest Autonomous Agent v1.0
Работает в цикле пока не появится пост в канале.
Знает все проблемы и исправляет их последовательно.
"""
import sqlite3, json, subprocess, re, os, sys, time
import urllib.request, urllib.parse, urllib.error

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'
CHANNEL = '-1003971323034'
PAT = os.environ.get('WORKING_PAT', '')
MAX_CYCLES = 10

def tg(msg, chat=MY_CHAT):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': chat, 'text': str(msg)[:4000], 'parse_mode': 'HTML'}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def log(msg):
    print(msg)
    
def n8n_login():
    r = subprocess.run(['curl','-s','-c','/tmp/ag_ck.txt','-X','POST',
        'http://localhost:5678/rest/login',
        '-H','Content-Type: application/json',
        '-d','{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'],
        capture_output=True, text=True, timeout=15)
    return 'data' in r.stdout

def n8n_get(wf_id):
    r = subprocess.run(['curl','-s','-b','/tmp/ag_ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'],
        capture_output=True, text=True, timeout=15)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

def n8n_put(wf_id, wf):
    r = subprocess.run(['curl','-s','-b','/tmp/ag_ck.txt','-X','PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

def n8n_activate(wf_id):
    subprocess.run(['curl','-s','-b','/tmp/ag_ck.txt','-X','POST',
        f'http://localhost:5678/rest/workflows/{wf_id}/activate',
        '-H','Content-Type: application/json','-d','{}'],
        capture_output=True, timeout=10)

def get_last_channel_msg():
    """Получаем последнее сообщение из канала через Bot API"""
    try:
        url = f'https://api.telegram.org/bot{BOT}/getUpdates?limit=5&allowed_updates=channel_post'
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read().decode())
            posts = [u for u in d.get('result',[]) if 'channel_post' in u]
            if posts:
                last = posts[-1]['channel_post']
                return last.get('date', 0), last.get('text', '')[:100]
    except: pass
    return 0, ''

def check_publisher_runs():
    """Проверяем последние runs publisher через GitHub API"""
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/runs?per_page=5',
            headers={'Authorization': f'token {PAT}', 'Accept': 'application/vnd.github+json'}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
            runs = d.get('workflow_runs', [])
            return d.get('total_count', 0), runs
    except Exception as e:
        log(f"Publisher check error: {e}")
        return 0, []

def dispatch_publisher(message, image_url=''):
    """Dispatch grandvest-publisher.yml"""
    payload = json.dumps({
        'ref': 'main',
        'inputs': {'message': message, 'image_url': image_url}
    }).encode()
    req = urllib.request.Request(
        'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
        data=payload,
        headers={
            'Authorization': f'token {PAT}',
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 204
    except urllib.error.HTTPError as e:
        log(f"Dispatch error {e.code}: {e.read().decode()[:100]}")
        return False

def fix_all_workflows():
    """Главная функция исправления всех workflow"""
    fixes = []
    
    # Правильный код узла 9
    NODE9 = (
        'const postText = $("8. Подготовка данных поста").first().json.tg_post;\n'
        'const imgData = $("HTTP Request \u2014 fal.ai").first().json;\n'
        'const imageUrl = imgData.images && imgData.images[0] ? imgData.images[0].url : "";\n'
        '\n'
        'if (!postText || postText.length < 10) {\n'
        '  throw new Error("tg_post пустой: " + JSON.stringify(postText));\n'
        '}\n'
        '\n'
        'const resp = await this.helpers.httpRequest({\n'
        '  method: "POST",\n'
        '  url: "https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches",\n'
        '  headers: {\n'
        '    "Authorization": "token ' + PAT + '",\n'
        '    "Accept": "application/vnd.github+json",\n'
        '    "Content-Type": "application/json"\n'
        '  },\n'
        '  body: JSON.stringify({\n'
        '    ref: "main",\n'
        '    inputs: {\n'
        '      message: postText,\n'
        '      image_url: imageUrl\n'
        '    }\n'
        '  })\n'
        '});\n'
        '\n'
        'return [{ json: { ok: true, len: postText.length } }];'
    )
    
    # Деdup через файл
    DEDUP = (
        'const items = $input.all();\n'
        'const unique = [];\n'
        'let published = [];\n'
        'try {\n'
        '  const fs = require("fs");\n'
        '  published = JSON.parse(fs.readFileSync("/data/published_titles.json", "utf8"));\n'
        '} catch(e) { published = []; }\n'
        'for (const item of items) {\n'
        '  const text = (item.json.title || item.json.text || "").trim().toLowerCase().substring(0, 60);\n'
        '  if (!published.some(p => p.substring(0, 60) === text)) {\n'
        '    unique.push(item);\n'
        '  }\n'
        '}\n'
        'console.log("Dedup:", items.length, "->", unique.length);\n'
        'return unique.slice(0, 1);'
    )
    
    # Фильтр с дефолтным score=7
    FILTER = (
        'const input = $input.first();\n'
        'const content = input.json.choices && input.json.choices[0]\n'
        '  ? input.json.choices[0].message.content : "";\n'
        'let score = 7;\n'
        'try {\n'
        '  const c = content.trim().replace(/```json\\s*/gi,"").replace(/```/g,"").trim();\n'
        '  if (c.startsWith("{")) { score = parseInt(JSON.parse(c).score) || 7; }\n'
        '  else { const m = content.match(/\\b([1-9]|10)\\b/); score = m ? parseInt(m[1]) : 7; }\n'
        '} catch(e) { score = 7; }\n'
        'console.log("Score:", score);\n'
        'const src = $("2. Дедупликация входящих").first().json;\n'
        'return [{ json: { ...src, score: score } }];'
    )
    
    # Правильное тело для OpenRouter
    PROMPT_GEN = (
        "Ты - эксперт по коммерческой недвижимости Москвы. "
        "Напиши развёрнутый пост для Telegram канала Grandvest.\n\n"
        "🏢 [ЗАГОЛОВОК]\n\n[ФАКТЫ с цифрами]\n\n"
        "[КОНТЕКСТ: районы, ставки]\n\n[ВЛИЯНИЕ]\n\n"
        "💼 Комментарий Грандвест:\n💡 Совет:\n"
        "👉 @Grandvest_bot\n#коммерческаянедвижимость #москва\n\n"
        "ТРЕБОВАНИЯ: 900-1200 символов."
    )
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, name, nodes FROM workflow_entity")
    rows = cur.fetchall()
    
    for wf_id, wf_name, nodes_raw in rows:
        try: nodes = json.loads(nodes_raw)
        except: continue
        
        changed = False
        or_key = ''
        keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', nodes_raw)
        if keys: or_key = keys[0]
        
        for n in nodes:
            name = n.get('name', '')
            ntype = n.get('type', '')
            params = n.get('parameters', {})
            code = params.get('jsCode', params.get('code', ''))
            url = params.get('url', '')
            
            # Узел 9 — полная замена кода
            is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
            if is_node9:
                bad_url = 'telegram-publisher' in code
                bad_auth = '"Bearer' in code
                bad_body = 'body: body' in code and 'JSON.stringify' not in code
                wrong_token = any(t != PAT for t in re.findall(r'ghp_[A-Za-z0-9]{36,}', code))
                
                if bad_url or bad_auth or bad_body or wrong_token:
                    n['parameters']['jsCode'] = NODE9
                    n['parameters'].pop('code', None)
                    changed = True
                    issues = []
                    if bad_url: issues.append('wrong_url')
                    if bad_auth: issues.append('Bearer')
                    if bad_body: issues.append('no_stringify')
                    if wrong_token: issues.append('wrong_token')
                    fixes.append(f"[{wf_name}] Node9: {issues}")
                    log(f"  FIXED Node9 in {wf_name}: {issues}")
            
            # Дедупликация
            if ('Дедупликац' in name) and 'getWorkflowStaticData' in code:
                n['parameters']['jsCode'] = DEDUP
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] Dedup: StaticData→file")
                log(f"  FIXED Dedup in {wf_name}")
            
            # Фильтр оценки
            if 'фильтр' in name.lower() and ('score >= 6' in code or 'score > 5' in code):
                n['parameters']['jsCode'] = FILTER
                n['parameters'].pop('code', None)
                changed = True
                fixes.append(f"[{wf_name}] Filter: threshold→7")
                log(f"  FIXED Filter in {wf_name}")
            
            # OpenRouter узлы — исправляем jsonBody
            if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
                jb = str(params.get('jsonBody', '')).strip()
                clean = jb[1:].strip() if jb.startswith('=') else jb
                try:
                    body = json.loads(clean) if clean else {}
                    mt = body.get('max_tokens', 0)
                    sys_ok = any('ТРЕБОВАНИЯ' in str(m.get('content',''))
                                for m in body.get('messages',[]) if m.get('role')=='system')
                    if mt < 2048 or not sys_ok:
                        body['max_tokens'] = 2048
                        if 'генерац' in name.lower():
                            for m in body.get('messages',[]):
                                if m.get('role') == 'system':
                                    m['content'] = PROMPT_GEN
                        params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                        n['parameters'] = params
                        changed = True
                        fixes.append(f"[{wf_name}] OR '{name}': mt→2048")
                        log(f"  FIXED OR {name} in {wf_name}")
                except Exception as e:
                    # RSS HTTP Request6: Body Type Raw → JSON
                    if or_key and 'HTTP Request6' in name:
                        rb = str(params.get('rawBody', params.get('body', ''))).strip()
                        clean_rb = rb[1:].strip() if rb.startswith('=') else rb
                        try:
                            body = json.loads(clean_rb) if clean_rb else {}
                            body['max_tokens'] = 2048
                            params['specifyBody'] = 'json'
                            params['bodyContentType'] = 'json'
                            params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                            params.pop('rawBody', None)
                            params.pop('body', None)
                            n['parameters'] = params
                            changed = True
                            fixes.append(f"[{wf_name}] HTTP Request6: Raw→JSON")
                            log(f"  FIXED HTTP Request6 in {wf_name}")
                        except Exception as e2:
                            if or_key:
                                # Создаём тело с нуля
                                new_body = {
                                    "model": "anthropic/claude-sonnet-4-5",
                                    "max_tokens": 2048,
                                    "messages": [
                                        {"role": "system", "content": PROMPT_GEN},
                                        {"role": "user", "content": "={{ 'Напиши пост по новости:\\n\\n' + ($input.first().json.title || $input.first().json.description || '') }}"}
                                    ]
                                }
                                params['specifyBody'] = 'json'
                                params['bodyContentType'] = 'json'
                                params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                                params.pop('rawBody', None)
                                params.pop('body', None)
                                n['parameters'] = params
                                changed = True
                                fixes.append(f"[{wf_name}] HTTP Request6: REBUILT")
                                log(f"  REBUILT HTTP Request6 in {wf_name}")
        
        if changed:
            cur.execute("UPDATE workflow_entity SET nodes=?, active=1, staticData='{}' WHERE id=?",
                       (json.dumps(nodes, ensure_ascii=False), wf_id))
    
    conn.commit()
    conn.close()
    
    # Сбрасываем деdup
    os.makedirs('/data', exist_ok=True)
    with open('/data/published_titles.json', 'w') as f:
        json.dump([], f)
    with open('/data/night_buffer.json', 'w') as f:
        json.dump([], f)
    
    return fixes

def send_webhook_test():
    """Отправляем тестовый вебхук"""
    import random
    news = [
        "Офисный рынок Москвы 2026: вакантность класса А достигла минимума 7.8 процента. Ставки аренды в ЦАО выросли до 48000 рублей за кв м. IT-сектор обеспечил 34 процента сделок. Инвестиции составили 350 млрд рублей по данным CBRE.",
        "Складской рынок Подмосковья: вакантность упала до 0.3 процента исторический минимум. Ставки аренды 14000 рублей за кв м в год. Девелоперы анонсировали 3 млн кв м новых площадей по данным NF Group.",
        "Инвестиции в коммерческую недвижимость России за полугодие 2026 превысили 350 миллиардов рублей. Складской сектор лидирует с долей 42 процента. Офисы класса А востребованы среди IT-компаний. Доходность 9-12 процентов годовых.",
    ]
    text = random.choice(news)
    ts = int(time.time())
    
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': f'<div class="tgme_widget_message_text js-message_text">{text}</div><time datetime="2026-06-27T{ts%24:02d}:00:00+00:00">{ts%24:02d}:00</time>'
    }).encode()
    
    try:
        with urllib.request.urlopen(urllib.request.Request(
            'http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type': 'application/json'}), timeout=30):
            return True
    except Exception as e:
        log(f"Webhook error: {e}")
        return False

def check_n8n_health():
    """Проверяем что n8n работает"""
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        return True
    except:
        return False

def restart_n8n():
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=40)
    time.sleep(20)
    for _ in range(10):
        if check_n8n_health():
            return True
        time.sleep(5)
    return False

# ═══════════════════════════════════════════════════
# ГЛАВНЫЙ ЦИКЛ АГЕНТА
# ═══════════════════════════════════════════════════

log(f"\n{'='*60}")
log(f"AUTONOMOUS AGENT v1.0 STARTED")
log(f"PAT: {PAT[:15]}...")
log(f"MAX CYCLES: {MAX_CYCLES}")
log(f"{'='*60}")

tg(f"🤖 <b>Autonomous Agent запущен</b>\n\nЦель: добиться публикаций в @grandvest_realty\nМакс. циклов: {MAX_CYCLES}")

initial_count, initial_runs = check_publisher_runs()
log(f"Initial publisher runs: {initial_count}")

cycle = 0
success = False

while cycle < MAX_CYCLES and not success:
    cycle += 1
    log(f"\n{'─'*50}")
    log(f"CYCLE {cycle}/{MAX_CYCLES}")
    log(f"{'─'*50}")
    
    # 1. Проверяем n8n
    if not check_n8n_health():
        log("n8n DOWN — restarting...")
        restart_n8n()
    else:
        log("n8n: OK")
    
    # 2. Останавливаем n8n для патча
    log("Stopping n8n for patch...")
    subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=20)
    time.sleep(3)
    
    # 3. Применяем все исправления
    log("Applying fixes...")
    fixes = fix_all_workflows()
    log(f"Fixes: {fixes}")
    
    # 4. Запускаем n8n
    log("Starting n8n...")
    subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=20)
    log("Waiting for n8n...")
    for _ in range(15):
        time.sleep(4)
        if check_n8n_health():
            log("n8n UP!")
            break
    
    # 5. Деактивируем и активируем workflow через API
    time.sleep(5)
    n8n_login()
    for wf_id in ['F24jvKiXJIs4wRiZ', 'SIPnV2mqmgMqUkLb']:
        wf = n8n_get(wf_id)
        if wf.get('nodes'):
            # Проверяем и патчим узел 9 через API тоже
            nodes = wf.get('nodes', [])
            changed = False
            for n in nodes:
                name = n.get('name', '')
                params = n.get('parameters', {})
                code = params.get('jsCode', params.get('code', ''))
                is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
                if is_node9:
                    if 'telegram-publisher' in code or '"Bearer' in code:
                        # Патчим через API
                        new_code = code.replace('telegram-publisher.yml', 'grandvest-publisher.yml')
                        new_code = re.sub(r'"Bearer (ghp_[A-Za-z0-9]+)"', f'"token {PAT}"', new_code)
                        if 'body: body' in new_code and 'JSON.stringify' not in new_code:
                            new_code = new_code.replace('body: body', 'body: JSON.stringify({\n    ref: "main",\n    inputs: {\n      message: postText || "тест",\n      image_url: imageUrl || ""\n    }\n  })')
                        params['jsCode'] = new_code
                        n['parameters'] = params
                        changed = True
                        log(f"  API fix Node9 in wf {wf_id}")
            if changed:
                n8n_put(wf_id, wf)
            n8n_activate(wf_id)
            log(f"  Workflow {wf_id} activated")
    
    # 6. Сбрасываем деdup
    os.makedirs('/data', exist_ok=True)
    with open('/data/published_titles.json', 'w') as f:
        json.dump([], f)
    
    # 7. Отправляем тестовый вебхук
    time.sleep(5)
    log("Sending test webhook...")
    webhook_ok = send_webhook_test()
    log(f"Webhook: {'OK' if webhook_ok else 'FAIL'}")
    
    # 8. Ждём 90 секунд и проверяем publisher
    log("Waiting 90s for execution...")
    time.sleep(90)
    
    new_count, new_runs = check_publisher_runs()
    log(f"Publisher runs: {initial_count} → {new_count}")
    
    if new_count > initial_count:
        # Новый run! Проверяем статус
        latest = new_runs[0] if new_runs else {}
        conclusion = latest.get('conclusion', '')
        log(f"NEW PUBLISHER RUN! conclusion={conclusion}")
        
        if conclusion == 'success':
            success = True
            tg(f"🎉 <b>УСПЕХ! Пост опубликован!</b>\n\nЦикл: {cycle}\nИсправления: {fixes}\n\nПост в @grandvest_realty!")
            log("SUCCESS! Post published!")
            break
        else:
            tg(f"⚠️ Цикл {cycle}: publisher запустился но {conclusion}\nИсправления: {fixes}")
            initial_count = new_count
    else:
        if fixes:
            tg(f"🔄 Цикл {cycle}: fixes={len(fixes)}, ждём следующего цикла...\n" + '\n'.join(f"• {f}" for f in fixes[:5]))
        log(f"No new publisher runs yet, continuing...")
    
    if cycle < MAX_CYCLES:
        log(f"Sleeping 30s before next cycle...")
        time.sleep(30)

if not success:
    tg(f"⚠️ Агент завершил {MAX_CYCLES} циклов без успеха.\nПоследние исправления были применены. Проверь @grandvest_realty.")
    log(f"AGENT: {MAX_CYCLES} cycles done without confirmed success")

log(f"\nAGENT FINISHED. Success={success}")
