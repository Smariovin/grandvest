#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
GH_PAT="${GH_PAT}"
DB="/opt/n8n/n8n_data/database.sqlite"

python3 << 'PYEOF'
import sqlite3, json, urllib.request, urllib.parse, subprocess, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
GH_PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def n8n_put(wf_id, wf_data):
    r = subprocess.run(['curl','-s','-b','/tmp/ck.txt','-X','PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf_data, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

# Login
subprocess.run(['curl','-s','-c','/tmp/ck.txt','-X','POST',
    'http://localhost:5678/rest/login',
    '-H','Content-Type: application/json',
    '-d','{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}'],
    capture_output=True, timeout=10)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

report = [f'<b>Full audit: {len(rows)} workflows</b>\n']
all_fixes = []

for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue

    report.append(f'\n<b>WF: {wf_name}</b> ({wf_id})')
    wf_changed = False

    # Ищем OR ключ в этом workflow
    or_key = ''
    for n in nodes:
        params = n.get('parameters', {})
        h_params = params.get('headerParameters', {}).get('parameters', [])
        for h in h_params:
            v = str(h.get('value', ''))
            if 'sk-or-v1' in v:
                or_key = v.replace('Bearer ', '').strip()
        # Также ищем в strings
        all_text = json.dumps(params)
        keys = re.findall(r'sk-or-v1-[a-f0-9]+', all_text)
        if keys: or_key = keys[0]

    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        url = params.get('url', '')
        code = params.get('jsCode', params.get('code', ''))

        # === ДИАГНОСТИКА: показываем все HTTP Request узлы ===
        if ntype == 'n8n-nodes-base.httpRequest':
            jb = params.get('jsonBody', '')
            specify = params.get('specifyBody', '')
            body_type = params.get('bodyContentType', '')
            send = params.get('sendBody', False)
            
            line = f'  [{name}] url={url[:50]} specifyBody={specify!r} bodyType={body_type!r}'
            report.append(line)
            print(line)
            
            if jb:
                jb_str = str(jb)
                print(f'    jsonBody({type(jb).__name__},{len(jb_str)}): {jb_str[:200]!r}')
                report.append(f'    jsonBody: {jb_str[:150]!r}')

        # === FIX: Узел 9 — отправка в Telegram ===
        is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        if is_node9 and 'code' in ntype.lower():
            has_pub = 'grandvest-publisher' in code
            has_old = 'api.telegram.org' in code or 'sendPhoto' in code
            if not has_pub or has_old:
                if GH_PAT:
                    n['parameters']['jsCode'] = (
                        f"const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
                        f"const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
                        f"if (!postText || postText.length < 10) {{ throw new Error('tg_post пустой'); }}\n"
                        f"const r = await this.helpers.httpRequest({{\n"
                        f"  method: 'POST',\n"
                        f"  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
                        f"  headers: {{'Authorization': 'token {GH_PAT}', 'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}},\n"
                        f"  body: JSON.stringify({{ref: 'main', inputs: {{message: postText, image_url: imageUrl}}}})\n"
                        f"}});\n"
                        f"return [{{json: {{ok: true, len: postText.length}}}}];"
                    )
                    n['parameters'].pop('code', None)
                    wf_changed = True
                    all_fixes.append(f'[{wf_name}] Node9 → grandvest-publisher')
                    print(f'  FIXED node9!')

        # === FIX: OpenRouter HTTP Request ===
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            jb = params.get('jsonBody', '')
            jb_str = str(jb).strip()
            
            # Убираем Expression prefix
            is_expr = jb_str.startswith('=')
            clean = jb_str[1:].strip() if is_expr else jb_str
            
            PROMPT = (
                "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
                "Пишешь развернутые посты для Telegram канала Grandvest. "
                "СТРУКТУРА: 🏢 [ЗАГОЛОВОК], [ФАКТЫ 3-4 предл с цифрами], "
                "[КОНТЕКСТ 3-4 предл: районы Москвы, ставки], "
                "[ВЛИЯНИЕ 2-3 предл], "
                "💼 Комментарий Грандвест: [2-3 предл], "
                "💡 Практический совет: [2 предл], "
                "👉 За подбором - @Grandvest_bot, "
                "#коммерческаянедвижимость #аренда #москва #грандвест. "
                "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика."
            )
            
            try:
                body = json.loads(clean)
                mt = body.get('max_tokens', 0)
                sys_ok = any('ТРЕБОВАНИЯ' in str(m.get('content','')) and '900' in str(m.get('content',''))
                             for m in body.get('messages',[]) if m.get('role')=='system')
                
                print(f'  OR node {name!r}: max_tokens={mt} sys_ok={sys_ok} is_expr={is_expr}')
                
                if mt < 2048 or not sys_ok:
                    body['max_tokens'] = 2048
                    for m in body.get('messages', []):
                        if m.get('role') == 'system':
                            m['content'] = PROMPT
                    # ВАЖНО: сохраняем БЕЗ = prefix
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    wf_changed = True
                    all_fixes.append(f'[{wf_name}] {name}: max_tokens→2048, prompt fixed')
                    print(f'  FIXED! Removed expr prefix: {is_expr}')
                    
            except json.JSONDecodeError as e:
                print(f'  JSONDecodeError on {name!r}: {e}')
                print(f'  clean: {clean[:200]!r}')
                # Если тело — динамический Expression с {{ }} — не трогаем
                if '{{' in clean or '$' in clean:
                    print(f'  → Dynamic expression, cannot modify automatically')
                    report.append(f'  ⚠️ {name}: dynamic expression body — needs manual fix in n8n UI')
                elif or_key:
                    # Пересоздаём с нуля
                    # Находим user message (обычно содержит $input или {{ expression }})
                    new_body = {
                        "model": "anthropic/claude-sonnet-4-5",
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": "Напиши пост о коммерческой недвижимости по этой новости: {{ $json.text || $json.title || $json.description || 'нет данных' }}"}
                        ]
                    }
                    params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                    n['parameters'] = params
                    wf_changed = True
                    all_fixes.append(f'[{wf_name}] {name}: rebuilt from scratch')
                    print(f'  REBUILT from scratch!')

    # Сохраняем
    if wf_changed:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))
        print(f'SQLite saved for {wf_name}')
        all_fixes.append(f'SQLite: {wf_name} saved')

cur.execute("UPDATE workflow_entity SET active=1")
conn.commit()
conn.close()

print(f'\n=== ALL FIXES ===')
for f in all_fixes: print(f'  {f}')

# Итоговый отчёт
msg = '\n'.join(report[:60])
if all_fixes:
    msg += '\n\n<b>Исправлено:</b>\n' + '\n'.join(f'✅ {f}' for f in all_fixes)
tg(msg)
print('Report sent to TG')
PYEOF
