#!/bin/bash
# IRON FIX: Исправляем оба workflow через n8n REST API
# 1. RSS HTTP Request6: Body Type Raw -> JSON
# 2. Парсер Telegram узел 9: заменяем токен
PAT="${WORKING_PAT}"
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

tg() {
    curl -s -X POST "https://api.telegram.org/bot${BOT}/sendMessage" \
        --data-urlencode "chat_id=${CHAT}" \
        --data-urlencode "text=$1" \
        --data-urlencode "parse_mode=HTML" > /dev/null 2>&1
}

# Логин в n8n
curl -s -c /tmp/iron_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null
echo "Logged in to n8n"

python3 << PYEOF
import subprocess, json, os, re, urllib.request, urllib.parse

PAT = os.environ.get('WORKING_PAT', '')
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def n8n_get(wf_id):
    r = subprocess.run(['curl','-s','-b','/tmp/iron_ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'],
        capture_output=True, text=True, timeout=15)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except Exception as e:
        print(f'GET error: {e} | {r.stdout[:100]}')
        return {}

def n8n_put(wf_id, wf_data):
    r = subprocess.run(['curl','-s','-b','/tmp/iron_ck.txt',
        '-X','PUT', f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf_data, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try:
        d = json.loads(r.stdout)
        return d.get('data', d)
    except:
        print(f'PUT error: {r.stdout[:200]}')
        return {}

PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы. "
    "Напиши развёрнутый пост для Telegram канала Grandvest.\n\n"
    "🏢 [ЗАГОЛОВОК]\n\n[ФАКТЫ с цифрами]\n\n"
    "[КОНТЕКСТ: районы, ставки руб/кв.м.]\n\n"
    "[ВЛИЯНИЕ на рынок]\n\n"
    "💼 Комментарий Грандвест:\n\n💡 Совет:\n\n"
    "👉 @Grandvest_bot\n#коммерческаянедвижимость #москва\n\n"
    "ТРЕБОВАНИЯ: 900-1200 символов. Только конкретика."
)

# Получаем все workflows
r = subprocess.run(['curl','-s','-b','/tmp/iron_ck.txt',
    'http://localhost:5678/rest/workflows'],
    capture_output=True, text=True, timeout=15)
all_wfs = json.loads(r.stdout).get('data', [])
print(f"Found {len(all_wfs)} workflows")

fixes = []

for wf_info in all_wfs:
    wf_id = wf_info['id']
    wf_name = wf_info['name']
    print(f"\n=== {wf_name} ({wf_id}) ===")
    
    wf = n8n_get(wf_id)
    nodes = wf.get('nodes', [])
    changed = False
    
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        
        # ════════════════════════════════════
        # ПРОБЛЕМА 1: RSS HTTP Request6 - Body Type Raw -> JSON
        # ════════════════════════════════════
        url = params.get('url', '')
        body_type = params.get('bodyContentType', params.get('rawContentType', ''))
        specify = params.get('specifyBody', '')
        
        if (name == 'HTTP Request6' or 'HTTP Request6' in name) and ntype == 'n8n-nodes-base.httpRequest':
            print(f"  Found HTTP Request6!")
            print(f"  bodyContentType: {body_type!r}")
            print(f"  specifyBody: {specify!r}")
            print(f"  url: {url[:60]}")
            
            # Читаем текущее тело запроса
            jb = params.get('jsonBody', '')
            rb = params.get('rawBody', params.get('body', ''))
            print(f"  jsonBody: {str(jb)[:100]!r}")
            print(f"  rawBody: {str(rb)[:100]!r}")
            
            # Получаем OR ключ из заголовков
            or_key = ''
            for h in params.get('headerParameters', {}).get('parameters', []):
                v = str(h.get('value', ''))
                if 'sk-or-v1' in v:
                    or_key = v.replace('Bearer ', '').strip()
            print(f"  OR key: {or_key[:20]}...")
            
            # Исправляем: меняем Body Type с Raw на JSON
            # Текущее тело из rawBody или jsonBody
            body_content = rb or jb or ''
            body_str = str(body_content).strip()
            
            # Если начинается с = (n8n expression) — убираем
            if body_str.startswith('='):
                body_str = body_str[1:].strip()
            
            try:
                body_data = json.loads(body_str)
                print(f"  Current body parsed OK: model={body_data.get('model','?')} max_tokens={body_data.get('max_tokens','?')}")
                # Обновляем параметры
                body_data['max_tokens'] = 2048
                for m in body_data.get('messages', []):
                    if m.get('role') == 'system':
                        m['content'] = PROMPT
                
                # Меняем Body Type на JSON
                params['specifyBody'] = 'json'
                params['bodyContentType'] = 'json'
                params['jsonBody'] = json.dumps(body_data, ensure_ascii=False)
                params.pop('rawBody', None)
                params.pop('body', None)
                n['parameters'] = params
                changed = True
                fixes.append(f"RSS HTTP Request6: Raw→JSON, max_tokens=2048")
                print(f"  ✅ FIXED: bodyContentType=json")
            except Exception as e:
                print(f"  Body parse error: {e}")
                print(f"  Raw body: {body_str[:200]!r}")
                
                # Создаём тело с нуля
                if or_key:
                    new_body = {
                        "model": "anthropic/claude-sonnet-4-5",
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": "={{ 'Напиши пост о коммерческой недвижимости по этой новости:\\n\\n' + ($input.first().json.title || $input.first().json.description || $input.first().json.text || 'нет данных') }}"}
                        ]
                    }
                    params['specifyBody'] = 'json'
                    params['bodyContentType'] = 'json'
                    params['jsonBody'] = json.dumps(new_body, ensure_ascii=False)
                    params.pop('rawBody', None)
                    params.pop('body', None)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"RSS HTTP Request6: REBUILT with json body")
                    print(f"  ✅ REBUILT from scratch")

        # ════════════════════════════════════
        # ПРОБЛЕМА 2: Узел 9 - 422 из-за неправильного токена
        # ════════════════════════════════════
        code = params.get('jsCode', params.get('code', ''))
        is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
        
        if is_node9 and ntype == 'n8n-nodes-base.code':
            tokens_in_code = re.findall(r'ghp_[A-Za-z0-9]{36,}', code)
            bad = [t for t in tokens_in_code if t != PAT]
            print(f"  Node9 '{name}': tokens={[t[:12] for t in tokens_in_code]} bad={[t[:12] for t in bad]}")
            
            if bad and PAT:
                new_code = code
                for b in bad:
                    new_code = new_code.replace(b, PAT)
                params['jsCode'] = new_code
                params.pop('code', None)
                n['parameters'] = params
                changed = True
                fixes.append(f"[{wf_name}] Node9: token {bad[0][:12]}→{PAT[:12]}")
                print(f"  ✅ FIXED: bad token replaced")
            elif not tokens_in_code and PAT and 'grandvest-publisher' in code:
                print(f"  Node9: no ghp_ tokens but has grandvest-publisher, OK")
            elif not PAT:
                print(f"  No PAT available!")
    
    if changed:
        print(f"  Saving {wf_name}...")
        result = n8n_put(wf_id, wf)
        saved = len(result.get('nodes', []))
        print(f"  Saved! {saved} nodes")
    else:
        print(f"  No changes needed")

print(f"\n=== FIXES APPLIED ===")
for f in fixes:
    print(f"  {f}")

if fixes:
    tg("✅ <b>Iron Fix applied:</b>\n" + '\n'.join(f"• {f}" for f in fixes))
else:
    tg("ℹ️ No fixes needed (all OK)")
PYEOF
