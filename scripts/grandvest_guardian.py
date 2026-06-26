#!/usr/bin/env python3
"""
Grandvest Guardian v1.1 — самодиагностика и самовосстановление
Использует subprocess curl для n8n API (надёжнее на VPS)
"""
import sqlite3, json, subprocess, re, os, sys
import urllib.request, urllib.parse
import datetime, time

DB = '/opt/n8n/n8n_data/database.sqlite'
STATUS_FILE = '/data/guardian_status.json'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')

def msk():
    utc = datetime.datetime.now(datetime.timezone.utc)
    return utc + datetime.timedelta(hours=3)

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': MY_CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e:
        print(f'TG error: {e}')

def load_status():
    try:
        with open(STATUS_FILE) as f: return json.load(f)
    except: return {}

def save_status(s):
    os.makedirs('/data', exist_ok=True)
    with open(STATUS_FILE, 'w') as f: json.dump(s, f, ensure_ascii=False, indent=2)

def curl_json(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout)
    except Exception as e:
        print(f'curl error: {e} | stdout: {r.stdout[:200] if r else ""}')
        return {}

def n8n_login():
    r = subprocess.run([
        'curl', '-s', '-c', '/tmp/n8n_cookies.txt', '-X', 'POST',
        'http://localhost:5678/rest/login',
        '-H', 'Content-Type: application/json',
        '-d', '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'
    ], capture_output=True, text=True, timeout=15)
    return 'data' in r.stdout

def n8n_get_wf(wf_id):
    r = subprocess.run([
        'curl', '-s', '-b', '/tmp/n8n_cookies.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'
    ], capture_output=True, text=True, timeout=15)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except:
        return {}

def n8n_put_wf(wf_id, wf_data):
    payload = json.dumps(wf_data, ensure_ascii=False)
    r = subprocess.run([
        'curl', '-s', '-b', '/tmp/n8n_cookies.txt',
        '-X', 'PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H', 'Content-Type: application/json',
        '-d', payload
    ], capture_output=True, text=True, timeout=20)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except:
        print(f'PUT error: {r.stdout[:200]}')
        return {}

CORRECT_PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА (строго):\n\n"
    "🏢 [ЗАГОЛОВОК 8-12 слов]\n\n"
    "По данным аналитиков, [факт+цифры]. [2-3 предложения деталей].\n\n"
    "[КОНТЕКСТ 3-4 предл]: районы Москвы, ставки руб/м², сравнение с прошлым.\n\n"
    "[ВЛИЯНИЕ 2-3 предл]: для арендаторов, инвесторов, собственников.\n\n"
    "💼 Комментарий Грандвест: [2-3 предл от агентства]\n\n"
    "💡 Практический совет: [2 конкретных предложения]\n\n"
    "👉 За подбором — @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика. Никакой воды."
)

def get_node9_code(pat):
    return (
        "// Отправка через GitHub Actions (api.telegram.org заблокирован с РФ)\n"
        "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
        "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
        "if (!postText || postText.length < 10) {\n"
        "  throw new Error('tg_post пустой: ' + JSON.stringify(postText));\n"
        "}\n"
        "console.log('Post:', postText.length, 'chars | Image:', !!imageUrl);\n"
        "const r = await this.helpers.httpRequest({\n"
        "  method: 'POST',\n"
        "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
        f"  headers: {{'Authorization': 'token {pat}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},\n"
        "  body: JSON.stringify({ref: 'main', inputs: {message: postText, image_url: imageUrl}})\n"
        "});\n"
        "console.log('GitHub dispatch OK');\n"
        "return [{json: {ok: true, len: postText.length}}];"
    )

# ════════════════════════════════════════════════
t = msk()
print(f"\n{'='*50}")
print(f"Grandvest Guardian v1.1 | {t.strftime('%d.%m.%Y %H:%M')} MSK")
print(f"{'='*50}")

prev = load_status()
curr = {'last_check': t.strftime('%d.%m.%Y %H:%M MSK')}
fixes = []
errors = []

# ── 1. n8n доступен ─────────────────────────────
print("\n[1] n8n health...")
try:
    urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
    curr['n8n'] = 'ok'
    print("  ✅ n8n running")
except:
    curr['n8n'] = 'down'
    print("  ❌ n8n DOWN — restarting...")
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=40)
    time.sleep(25)
    fixes.append("n8n перезапущен (был недоступен)")

# ── 2. Login и проверка workflow ─────────────────
print("\n[2] n8n workflow check...")
if n8n_login():
    print("  ✅ n8n login OK")
    wf = n8n_get_wf('F24jvKiXJIs4wRiZ')
    nodes = wf.get('nodes', [])
    print(f"  Nodes: {len(nodes)}")
    wf_changed = False

    for n in nodes:
        name = n.get('name', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))

        # ── Узел 9 ──────────────────────────────
        if 'Отправка' in name or ('9.' in name and 'Telegram' in name):
            has_pub = 'grandvest-publisher' in code
            has_old = 'api.telegram.org' in code or 'sendPhoto' in code
            ok9 = has_pub and not has_old
            curr['node9'] = 'ok' if ok9 else 'broken'
            print(f"  {'✅' if ok9 else '❌'} Node9 '{name}': pub={has_pub} old_api={has_old}")

            if not ok9:
                if GH_PAT:
                    n['parameters']['jsCode'] = get_node9_code(GH_PAT)
                    n['parameters'].pop('code', None)
                    wf_changed = True
                    fixes.append(f"Узел 9 восстановлен → grandvest-publisher.yml")
                    curr['node9'] = 'fixed'
                    print("    → FIXED!")
                else:
                    errors.append("Узел 9 сломан но GH_PAT недоступен")

        # ── Узел генерации ───────────────────────
        if name == 'HTTP Request — генерация поста':
            jb = params.get('jsonBody', '{}')
            try:
                body = json.loads(jb) if isinstance(jb, str) else jb
                mt = body.get('max_tokens', 0)
                sys_msg = next((m['content'] for m in body.get('messages',[]) if m.get('role')=='system'), '')
                prompt_ok = 'ТРЕБОВАНИЯ' in sys_msg and ('900' in sys_msg or '1200' in sys_msg)
                tokens_ok = mt >= 2048
                gen_ok = prompt_ok and tokens_ok
                curr['generation'] = 'ok' if gen_ok else 'broken'
                print(f"  {'✅' if gen_ok else '❌'} Generation: max_tokens={mt} prompt={'ok' if prompt_ok else 'SHORT'}")

                if not gen_ok:
                    body['max_tokens'] = 2048
                    for m in body.get('messages', []):
                        if m.get('role') == 'system':
                            m['content'] = CORRECT_PROMPT
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    wf_changed = True
                    fixes.append(f"Генерация: max_tokens {mt}→2048, промпт 900-1200 символов")
                    curr['generation'] = 'fixed'
                    print("    → FIXED!")
            except Exception as e:
                print(f"  ❌ Generation parse error: {e}")
                errors.append(f"Ошибка разбора узла генерации: {e}")

    # Сохраняем если были изменения
    if wf_changed:
        result = n8n_put_wf('F24jvKiXJIs4wRiZ', wf)
        if result.get('nodes'):
            print(f"  ✅ Workflow saved! {len(result['nodes'])} nodes")
        else:
            print(f"  ⚠️ PUT result: {str(result)[:100]}")
else:
    errors.append("n8n login failed")
    print("  ❌ n8n login FAILED")

# ── 3. Дедупликация ──────────────────────────────
print("\n[3] Dedup file...")
try:
    with open('/data/published_titles.json') as f:
        dedup = json.load(f)
    count = len(dedup)
    curr['dedup'] = count
    print(f"  ✅ {count} записей")
    if count > 500:
        with open('/data/published_titles.json', 'w') as f:
            json.dump(dedup[-200:], f, ensure_ascii=False)
        fixes.append(f"Дедупликация очищена: {count}→200")
except FileNotFoundError:
    os.makedirs('/data', exist_ok=True)
    with open('/data/published_titles.json', 'w') as f: json.dump([], f)
    print("  ℹ️ Создан пустой файл дедупликации")
except Exception as e:
    print(f"  ❌ {e}")
    errors.append(f"Дедупликация: {e}")

# ── Итог ─────────────────────────────────────────
all_ok = not errors
curr['status'] = 'OK' if all_ok else 'ERRORS'
save_status(curr)

print(f"\n{'='*50}")
print(f"{'✅ ALL OK' if all_ok else '❌ ERRORS'}")
if fixes: print(f"FIXED: {fixes}")
if errors: print(f"ERRORS: {errors}")

# Telegram — только при изменениях
if fixes or (errors and prev.get('status')=='OK') or (all_ok and prev.get('status')=='ERRORS'):
    if fixes and all_ok:
        tg(f"✅ <b>Guardian исправил:</b>\n" + '\n'.join(f'• {f}' for f in fixes) + f"\n\n🕐 {curr['last_check']}")
    elif errors:
        tg(f"⚠️ <b>Guardian: ошибки</b>\n" + '\n'.join(f'❌ {e}' for e in errors) +
           (('\n\n✅ ' + '\n'.join(f'• {f}' for f in fixes)) if fixes else '') + f"\n\n🕐 {curr['last_check']}")
