#!/usr/bin/env python3
"""
Grandvest Guardian v2.0
Следит за ОБОИМИ workflows и исправляет:
- Парсер Telegram (F24jvKiXJIs4wRiZ): узел 9 + генерация поста
- RSS Сбор (SIPnV2mqmgMqUkLb): HTTP Request6 + генерация
"""
import sqlite3, json, subprocess, re, os, sys
import urllib.request, urllib.parse
import datetime, time

DB = '/opt/n8n/n8n_data/database.sqlite'
STATUS_FILE = '/data/guardian_status.json'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')

WF_PARSER = 'F24jvKiXJIs4wRiZ'   # Парсер Telegram
WF_RSS    = 'SIPnV2mqmgMqUkLb'   # Сбор новостей RSS

# ── Helpers ──────────────────────────────────────────────
def msk():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

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

def n8n_login():
    r = subprocess.run([
        'curl', '-s', '-c', '/tmp/n8n_ck.txt', '-X', 'POST',
        'http://localhost:5678/rest/login',
        '-H', 'Content-Type: application/json',
        '-d', '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'
    ], capture_output=True, text=True, timeout=15)
    return 'data' in r.stdout

def n8n_get(wf_id):
    r = subprocess.run([
        'curl', '-s', '-b', '/tmp/n8n_ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'
    ], capture_output=True, text=True, timeout=15)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except Exception as e:
        print(f'  GET error: {e} | {r.stdout[:100]}')
        return {}

def n8n_put(wf_id, wf_data):
    r = subprocess.run([
        'curl', '-s', '-b', '/tmp/n8n_ck.txt',
        '-X', 'PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(wf_data, ensure_ascii=False)
    ], capture_output=True, text=True, timeout=20)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except Exception as e:
        print(f'  PUT error: {e} | {r.stdout[:200]}')
        return {}

# ── Правильные значения ──────────────────────────────────
CORRECT_PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА (строго соблюдай):\n\n"
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

def fix_openrouter_body(params, node_name):
    """
    Исправляет параметры HTTP Request узла с OpenRouter.
    Работает с любым форматом хранения jsonBody.
    Возвращает (исправленные params, описание что исправлено) или (None, None)
    """
    changes = []

    # Читаем jsonBody в любом формате
    jb_raw = params.get('jsonBody', '')
    jb_str = str(jb_raw) if jb_raw else ''

    # Если пустой — создаём правильную структуру
    if not jb_str.strip() or jb_str.strip() in ('{}', '""', "''"):
        print(f'  ⚠️  {node_name}: jsonBody пустой — перезаписываем')
        # Определяем модель по контексту
        model = 'anthropic/claude-sonnet-4-5'
        # Ищем ключ OR в окружении
        or_key = os.environ.get('OR_KEY', '')
        if not or_key:
            # Пробуем найти в других параметрах
            headers = params.get('headerParameters', {}).get('parameters', [])
            for h in headers:
                if 'Bearer' in str(h.get('value', '')):
                    or_key = h['value'].replace('Bearer ', '').strip()

        if not or_key:
            return None, None

        new_body = {
            "model": model,
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": CORRECT_PROMPT},
                {"role": "user", "content": "={{ 'Напиши пост о коммерческой недвижимости по новости:\\n\\n' + $input.first().json.text }}"}
            ]
        }
        params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
        params['specifyBody'] = 'json'
        params['bodyContentType'] = 'json'
        changes.append("jsonBody создан заново")
        return params, changes

    # Парсим существующий jsonBody
    try:
        # Убираем n8n expression обёртку если есть ={{...}}
        clean = jb_str.strip()
        if clean.startswith('={{') and clean.endswith('}}'):
            # Это n8n expression — нельзя менять напрямую
            print(f'  ℹ️  {node_name}: jsonBody — n8n Expression, пропускаем')
            return None, None

        body = json.loads(clean)
        modified = False

        # Проверяем max_tokens
        mt = body.get('max_tokens', 0)
        if mt < 2048:
            body['max_tokens'] = 2048
            changes.append(f'max_tokens {mt}→2048')
            modified = True

        # Проверяем системный промпт
        for msg in body.get('messages', []):
            if msg.get('role') == 'system':
                content = msg.get('content', '')
                if 'ТРЕБОВАНИЯ' not in content or ('900' not in content and '1200' not in content):
                    msg['content'] = CORRECT_PROMPT
                    changes.append('промпт расширен до 900-1200 символов')
                    modified = True

        if modified:
            params['jsonBody'] = json.dumps(body, ensure_ascii=False)
            return params, changes

    except json.JSONDecodeError as e:
        print(f'  ❌ {node_name}: JSONDecodeError: {e}')
        print(f'  Raw jsonBody: {jb_str[:200]!r}')
        # Если не JSON — возможно хранится в другом поле
        # Проверяем 'body'
        body_raw = params.get('body', '')
        if body_raw and isinstance(body_raw, str):
            try:
                body = json.loads(body_raw)
                mt = body.get('max_tokens', 0)
                if mt < 2048:
                    body['max_tokens'] = 2048
                    changes.append(f'body.max_tokens {mt}→2048')
                for msg in body.get('messages', []):
                    if msg.get('role') == 'system':
                        content = msg.get('content', '')
                        if 'ТРЕБОВАНИЯ' not in content:
                            msg['content'] = CORRECT_PROMPT
                            changes.append('body промпт расширен')
                params['body'] = json.dumps(body, ensure_ascii=False)
                return params, changes
            except:
                pass

    return None, None

# ════════════════════════════════════════════════════════
t = msk()
print(f"\n{'='*55}")
print(f"Grandvest Guardian v2.0 | {t.strftime('%d.%m.%Y %H:%M')} MSK")
print(f"{'='*55}")

prev = load_status()
curr = {'ts': t.strftime('%d.%m.%Y %H:%M MSK')}
fixes = []
errors = []

# ── 1. n8n health ────────────────────────────────────────
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
    fixes.append("🔄 n8n перезапущен (был недоступен)")

# ── 2. Логин ─────────────────────────────────────────────
print("\n[2] n8n login...")
if not n8n_login():
    errors.append("❌ n8n login failed")
    print("  ❌ Login FAILED")
else:
    print("  ✅ Login OK")

    # ── 3. Обходим ОБА workflow ───────────────────────────
    WORKFLOWS = {
        WF_PARSER: 'Парсер Telegram',
        WF_RSS:    'Сбор новостей RSS'
    }

    for wf_id, wf_label in WORKFLOWS.items():
        print(f"\n[3] Workflow: {wf_label} ({wf_id})")
        wf = n8n_get(wf_id)
        if not wf or not wf.get('nodes'):
            print(f"  ❌ Не удалось получить workflow")
            errors.append(f"❌ {wf_label}: workflow недоступен")
            continue

        nodes = wf.get('nodes', [])
        print(f"  Nodes: {len(nodes)}")
        wf_changed = False

        for n in nodes:
            name = n.get('name', '')
            ntype = n.get('type', '')
            params = n.get('parameters', {})
            code = params.get('jsCode', params.get('code', ''))
            url = params.get('url', '')

            # ── Узел 9: Отправка в Telegram (только Парсер) ──
            if wf_id == WF_PARSER and ('Отправка' in name or ('9.' in name and 'Telegram' in name)):
                has_pub = 'grandvest-publisher' in code
                has_old = 'api.telegram.org' in code or 'sendPhoto' in code
                ok = has_pub and not has_old
                icon = '✅' if ok else '❌'
                print(f"  {icon} Node9 '{name}': publisher={has_pub} old_api={has_old}")
                curr[f'{wf_id}_node9'] = 'ok' if ok else 'broken'

                if not ok:
                    if GH_PAT:
                        n['parameters']['jsCode'] = get_node9_code(GH_PAT)
                        n['parameters'].pop('code', None)
                        wf_changed = True
                        fixes.append(f"✅ [{wf_label}] Узел 9 → grandvest-publisher.yml")
                        curr[f'{wf_id}_node9'] = 'fixed'
                        print("    → FIXED!")
                    else:
                        errors.append(f"❌ [{wf_label}] Узел 9 сломан, нет GH_PAT")

            # ── HTTP Request узлы с OpenRouter ───────────────
            if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
                print(f"  🔍 OpenRouter node: '{name}'")
                jb = params.get('jsonBody', '')
                jb_str = str(jb)

                # Читаем текущее состояние
                ok_prompt = False
                ok_tokens = False
                try:
                    body = json.loads(jb_str)
                    mt = body.get('max_tokens', 0)
                    ok_tokens = mt >= 2048
                    sys_c = next((m['content'] for m in body.get('messages',[]) if m.get('role')=='system'), '')
                    ok_prompt = 'ТРЕБОВАНИЯ' in sys_c and ('900' in sys_c or '1200' in sys_c)
                    print(f"    max_tokens={mt} {'✅' if ok_tokens else '❌'} | prompt={'ok ✅' if ok_prompt else 'short ❌'}")
                    curr[f'{wf_id}_{name}_gen'] = 'ok' if (ok_tokens and ok_prompt) else 'broken'
                except Exception as e:
                    print(f"    ❌ Parse error: {e}")
                    print(f"    jsonBody raw: {jb_str[:150]!r}")
                    curr[f'{wf_id}_{name}_gen'] = 'parse_error'

                if not ok_tokens or not ok_prompt:
                    new_params, changes = fix_openrouter_body(params, name)
                    if new_params and changes:
                        n['parameters'] = new_params
                        wf_changed = True
                        desc = f"[{wf_label}] '{name}': {', '.join(changes)}"
                        fixes.append(f"✅ {desc}")
                        curr[f'{wf_id}_{name}_gen'] = 'fixed'
                        print(f"    → FIXED: {changes}")
                    else:
                        errors.append(f"⚠️ [{wf_label}] '{name}': не удалось исправить (Expression или нет ключа)")

        # Сохраняем workflow если были изменения
        if wf_changed:
            print(f"\n  💾 Saving {wf_label}...")
            result = n8n_put(wf_id, wf)
            saved_nodes = len(result.get('nodes', []))
            if saved_nodes > 0:
                print(f"  ✅ Saved! {saved_nodes} nodes")
            else:
                print(f"  ⚠️ PUT result unclear: {str(result)[:100]}")

# ── 4. Дедупликация ──────────────────────────────────────
print("\n[4] Dedup...")
try:
    with open('/data/published_titles.json') as f:
        dedup = json.load(f)
    count = len(dedup)
    curr['dedup'] = count
    if count > 500:
        with open('/data/published_titles.json', 'w') as f:
            json.dump(dedup[-200:], f, ensure_ascii=False)
        fixes.append(f"✅ Дедупликация: {count}→200 записей")
        print(f"  ✅ Очищена: {count}→200")
    else:
        print(f"  ✅ {count} записей")
except FileNotFoundError:
    os.makedirs('/data', exist_ok=True)
    with open('/data/published_titles.json', 'w') as f: json.dump([], f)
    print("  ℹ️ Создан")
except Exception as e:
    errors.append(f"❌ Дедупликация: {e}")
    print(f"  ❌ {e}")

# ── 5. Night buffer ──────────────────────────────────────
print("\n[5] Night buffer...")
try:
    with open('/data/night_buffer.json') as f:
        buf = json.load(f)
    curr['buffer'] = len(buf)
    print(f"  ✅ {len(buf)} записей")
except:
    os.makedirs('/data', exist_ok=True)
    with open('/data/night_buffer.json', 'w') as f: json.dump([], f)
    curr['buffer'] = 0
    print("  ℹ️ Создан")

# ── Итог ─────────────────────────────────────────────────
all_ok = not errors
curr['status'] = 'OK' if all_ok else 'ERRORS'
save_status(curr)

print(f"\n{'='*55}")
print(f"{'✅ ALL OK' if all_ok else '❌ ERRORS'}")
if fixes: print("FIXED:\n  " + "\n  ".join(fixes))
if errors: print("ERRORS:\n  " + "\n  ".join(errors))
print(f"{'='*55}")

# TG уведомление
prev_ok = prev.get('status') == 'OK'
send = bool(fixes) or (errors and prev_ok) or (all_ok and not prev_ok)

if send:
    if fixes and all_ok:
        tg(f"✅ <b>Guardian исправил:</b>\n" + '\n'.join(fixes) + f"\n\n🕐 {curr['ts']}")
    elif errors:
        err_txt = '\n'.join(errors)
        fix_txt = ('\n\n✅ Исправлено:\n' + '\n'.join(fixes)) if fixes else ''
        tg(f"⚠️ <b>Guardian: ошибки</b>\n{err_txt}{fix_txt}\n\n🕐 {curr['ts']}")
