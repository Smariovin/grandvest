#!/usr/bin/env python3
"""
Grandvest Guardian v1.0
Самодиагностика и самовосстановление 24/7

Запускается каждые 30 минут вместе с парсером.
Проверяет 8 критических условий и немедленно чинит найденные проблемы.
Отправляет отчёт только при изменении статуса (не спамит).
"""
import sqlite3, json, subprocess, re, os, sys
import urllib.request, urllib.parse, urllib.error
import datetime, time

DB = '/opt/n8n/n8n_data/database.sqlite'
STATUS_FILE = '/data/guardian_status.json'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')
OR_KEY = os.environ.get('OR_KEY', '')

# ─── Telegram ───────────────────────────────────────────
def tg(msg, chat=MY_CHAT):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': chat, 'text': msg[:4000], 'parse_mode': 'HTML'
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e:
        print(f'TG error: {e}')

# ─── Статус (чтобы не спамить повторными алертами) ──────
def load_status():
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_status(s):
    os.makedirs('/data', exist_ok=True)
    with open(STATUS_FILE, 'w') as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

# ─── n8n API ────────────────────────────────────────────
def n8n_login():
    try:
        req = urllib.request.Request(
            'http://localhost:5678/rest/login',
            data=json.dumps({'emailOrLdapLoginId': 'admin@grandvest.ru',
                           'password': 'Grandvest2026!'}).encode(),
            headers={'Content-Type': 'application/json'})
        # Используем CookieJar
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        opener.open(req, timeout=10)
        return opener, cj
    except Exception as e:
        print(f'n8n login error: {e}')
        return None, None

def n8n_get_workflow(opener, wf_id):
    try:
        with opener.open(f'http://localhost:5678/rest/workflows/{wf_id}', timeout=10) as r:
            d = json.loads(r.read().decode())
            return d.get('data', d)
    except Exception as e:
        print(f'n8n get workflow error: {e}')
        return None

def n8n_put_workflow(opener, wf_id, wf_data):
    try:
        req = urllib.request.Request(
            f'http://localhost:5678/rest/workflows/{wf_id}',
            data=json.dumps(wf_data, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json'},
            method='PUT')
        with opener.open(req, timeout=15) as r:
            d = json.loads(r.read().decode())
            return d.get('data', d)
    except Exception as e:
        print(f'n8n PUT error: {e}')
        return None

def n8n_activate(opener, wf_id):
    try:
        req = urllib.request.Request(
            f'http://localhost:5678/rest/workflows/{wf_id}/activate',
            data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
        opener.open(req, timeout=10)
        return True
    except:
        return False

def docker_restart():
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=40)
    time.sleep(20)

# ─── Правильные значения ─────────────────────────────────
CORRECT_SYSTEM_PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь развёрнутые, аналитические посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА:\n\n"
    "🏢 [ЗАГОЛОВОК - суть новости 8-12 слов]\n\n"
    "По данным аналитиков, [факт с цифрами]. [Развитие мысли 2-3 предложения]. [Итог абзаца].\n\n"
    "[КОНТЕКСТ - 3-4 предложения]: причины, конкретные районы Москвы, ставки аренды руб/м², сравнение с прошлым периодом.\n\n"
    "[ВЛИЯНИЕ - 2-3 предложения]: что означает для арендаторов, инвесторов, собственников?\n\n"
    "💼 Комментарий Грандвест: [2-3 предложения - профессиональная оценка агентства]\n\n"
    "💡 Практический совет: [2 конкретных предложения что делать прямо сейчас]\n\n"
    "👉 За подбором объекта — @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика и цифры. Никакой воды."
)

def get_correct_node9_code(pat):
    return f"""// Отправка в Telegram через GitHub Actions (api.telegram.org заблокирован с РФ)
const postText = $('8. Подготовка данных поста').first().json.tg_post;
const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';

if (!postText || postText.length < 10) {{
  throw new Error('tg_post пустой: ' + JSON.stringify(postText));
}}
console.log('Post:', postText.length, 'chars | Image:', !!imageUrl);

const r = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
  headers: {{
    'Authorization': 'token {pat}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github+json'
  }},
  body: JSON.stringify({{ ref: 'main', inputs: {{ message: postText, image_url: imageUrl }} }})
}});

console.log('GitHub dispatch OK');
return [{{ json: {{ ok: true, len: postText.length }} }}];"""

# ─── ПРОВЕРКИ ────────────────────────────────────────────
def run_checks():
    msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    print(f"\n{'='*50}")
    print(f"Grandvest Guardian | {msk.strftime('%d.%m.%Y %H:%M')} MSK")
    print(f"{'='*50}")

    fixes = []
    errors = []
    prev_status = load_status()
    curr_status = {}

    # ── 1. n8n запущен ──────────────────────────────────
    print("\n[1] n8n status...")
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        curr_status['n8n'] = 'ok'
        print("  ✅ n8n running")
    except:
        curr_status['n8n'] = 'down'
        print("  ❌ n8n DOWN - restarting...")
        docker_restart()
        fixes.append("n8n был недоступен — перезапущен")

    # ── 2. Подключение к SQLite ──────────────────────────
    print("\n[2] SQLite & workflows...")
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM workflow_entity")
        wfs = dict(cur.fetchall())
        conn.close()
        curr_status['sqlite'] = 'ok'
        print(f"  ✅ SQLite OK | Workflows: {list(wfs.values())}")
    except Exception as e:
        curr_status['sqlite'] = 'error'
        errors.append(f"SQLite недоступен: {e}")
        print(f"  ❌ SQLite error: {e}")

    # ── 3. Парсер workflow активен ───────────────────────
    print("\n[3] Workflow active status...")
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT id, name, active FROM workflow_entity")
        for wid, wname, active in cur.fetchall():
            status = 'active' if active else 'inactive'
            curr_status[f'wf_{wid}'] = status
            icon = '✅' if active else '❌'
            print(f"  {icon} {wname}: {status}")
            if not active:
                errors.append(f"Workflow '{wname}' неактивен")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")

    # ── 4. Узел 9 — правильный код ───────────────────────
    print("\n[4] Node 9 code check...")
    opener, _ = n8n_login()
    if opener:
        wf = n8n_get_workflow(opener, 'F24jvKiXJIs4wRiZ')
        if wf:
            nodes = wf.get('nodes', [])
            node9_ok = False
            generation_ok = False

            for n in nodes:
                name = n.get('name', '')
                params = n.get('parameters', {})
                code = params.get('jsCode', params.get('code', ''))

                # Проверяем узел 9
                if 'Отправка' in name or ('9.' in name and 'Telegram' in name):
                    has_publisher = 'grandvest-publisher' in code
                    has_direct_tg = 'api.telegram.org' in code or 'sendPhoto' in code
                    node9_ok = has_publisher and not has_direct_tg
                    curr_status['node9'] = 'ok' if node9_ok else 'broken'
                    print(f"  {'✅' if node9_ok else '❌'} Node 9: publisher={has_publisher}, direct_tg={has_direct_tg}")

                    if not node9_ok and GH_PAT:
                        print("    → FIXING node 9...")
                        n['parameters']['jsCode'] = get_correct_node9_code(GH_PAT)
                        n['parameters'].pop('code', None)
                        result = n8n_put_workflow(opener, 'F24jvKiXJIs4wRiZ', wf)
                        if result:
                            fixes.append("Узел 9 восстановлен: grandvest-publisher.yml dispatch")
                            node9_ok = True
                            curr_status['node9'] = 'fixed'
                            print("    ✅ Node 9 fixed!")
                        else:
                            errors.append("Не удалось исправить узел 9")

                # Проверяем узел генерации поста
                if name == 'HTTP Request — генерация поста':
                    json_body = params.get('jsonBody', '')
                    try:
                        body = json.loads(json_body) if isinstance(json_body, str) else json_body
                        mt = body.get('max_tokens', 0)
                        msgs = body.get('messages', [])
                        sys_content = ''
                        for msg in msgs:
                            if msg.get('role') == 'system':
                                sys_content = msg.get('content', '')

                        prompt_ok = '900' in sys_content or '1200' in sys_content or 'ТРЕБОВАНИЯ' in sys_content
                        tokens_ok = mt >= 2048
                        generation_ok = prompt_ok and tokens_ok
                        curr_status['generation'] = 'ok' if generation_ok else 'broken'
                        print(f"  {'✅' if generation_ok else '❌'} Generation: max_tokens={mt} (need≥2048), prompt={'ok' if prompt_ok else 'SHORT'}")

                        if not generation_ok:
                            print("    → FIXING generation node...")
                            body['max_tokens'] = 2048
                            for msg in body.get('messages', []):
                                if msg.get('role') == 'system':
                                    msg['content'] = CORRECT_SYSTEM_PROMPT
                            params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                            n['parameters'] = params
                            result = n8n_put_workflow(opener, 'F24jvKiXJIs4wRiZ', wf)
                            if result:
                                fixes.append(f"Узел генерации: max_tokens {mt}→2048, промпт расширен до 900-1200 символов")
                                generation_ok = True
                                curr_status['generation'] = 'fixed'
                                print("    ✅ Generation fixed!")
                            else:
                                errors.append("Не удалось исправить узел генерации")
                    except Exception as e:
                        print(f"  ❌ Generation parse error: {e}")
                        errors.append(f"Ошибка чтения узла генерации: {e}")

    # ── 5. Дедупликация файл ─────────────────────────────
    print("\n[5] Dedup file...")
    try:
        with open('/data/published_titles.json') as f:
            dedup = json.load(f)
        count = len(dedup)
        curr_status['dedup_count'] = count
        print(f"  ✅ Dedup: {count} записей")
        if count > 500:
            print(f"  ⚠️ Много записей ({count}), очищаем старые...")
            dedup = dedup[-200:]  # оставляем последние 200
            with open('/data/published_titles.json', 'w') as f:
                json.dump(dedup, f, ensure_ascii=False)
            fixes.append(f"Дедупликация очищена: {count}→200 записей")
    except FileNotFoundError:
        print("  ⚠️ Dedup file missing, creating...")
        os.makedirs('/data', exist_ok=True)
        with open('/data/published_titles.json', 'w') as f:
            json.dump([], f)
        fixes.append("Создан файл дедупликации")
    except Exception as e:
        print(f"  ❌ Dedup error: {e}")
        errors.append(f"Ошибка дедупликации: {e}")

    # ── 6. Ночной буфер ──────────────────────────────────
    print("\n[6] Night buffer...")
    try:
        with open('/data/night_buffer.json') as f:
            buf = json.load(f)
        curr_status['buffer'] = len(buf)
        print(f"  ✅ Buffer: {len(buf)} записей")
    except FileNotFoundError:
        os.makedirs('/data', exist_ok=True)
        with open('/data/night_buffer.json', 'w') as f:
            json.dump([], f)
        curr_status['buffer'] = 0
        print("  ℹ️ Buffer file created (empty)")
    except Exception as e:
        print(f"  ❌ Buffer error: {e}")

    # ─── Итог ────────────────────────────────────────────
    total_ok = len(errors) == 0
    curr_status['last_check'] = msk.strftime('%d.%m.%Y %H:%M MSK')
    curr_status['status'] = 'OK' if total_ok else 'ERRORS'

    save_status(curr_status)

    print(f"\n{'='*50}")
    print(f"RESULT: {'✅ ALL OK' if total_ok else '❌ ERRORS FOUND'}")
    if fixes: print(f"FIXED: {fixes}")
    if errors: print(f"ERRORS: {errors}")
    print(f"{'='*50}")

    # Отправляем Telegram отчёт только если:
    # - были исправления
    # - появились новые ошибки
    # - статус изменился с ошибки на OK
    prev_ok = prev_status.get('status') == 'OK'
    send_report = bool(fixes) or (errors and prev_ok) or (not errors and not prev_ok)

    if send_report:
        if fixes and not errors:
            msg = (f"✅ <b>Guardian: исправлено</b>\n\n"
                   + '\n'.join(f"• {f}" for f in fixes)
                   + f"\n\n🕐 {curr_status['last_check']}")
        elif errors:
            msg = (f"⚠️ <b>Guardian: обнаружены проблемы</b>\n\n"
                   + '\n'.join(f"❌ {e}" for e in errors)
                   + (('\n\n✅ Исправлено:\n' + '\n'.join(f"• {f}" for f in fixes)) if fixes else '')
                   + f"\n\n🕐 {curr_status['last_check']}")
        else:
            msg = None

        if msg:
            tg(msg)

    return total_ok, fixes, errors

if __name__ == '__main__':
    ok, fixes, errors = run_checks()
    sys.exit(0 if ok else 1)
