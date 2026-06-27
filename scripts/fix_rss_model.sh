#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/rm_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Получаем все workflows и находим RSS
curl -s -b /tmp/rm_ck.txt 'http://localhost:5678/rest/workflows' | \
python3 << 'PYEOF'
import sys, json, subprocess, urllib.request, urllib.parse, re

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

def n8n_put(wf_id, wf_data):
    r = subprocess.run(['curl','-s','-b','/tmp/rm_ck.txt','-X','PUT',
        f'http://localhost:5678/rest/workflows/{wf_id}',
        '-H','Content-Type: application/json',
        '-d', json.dumps(wf_data, ensure_ascii=False)],
        capture_output=True, text=True, timeout=20)
    try: return json.loads(r.stdout).get('data', {})
    except: return {}

d = json.load(sys.stdin)
all_wfs = d.get('data', [])
print(f"Total workflows: {len(all_wfs)}")

fixes = []

for wf_info in all_wfs:
    wf_id = wf_info['id']
    wf_name = wf_info['name']
    
    # Получаем детали workflow
    r = subprocess.run(['curl','-s','-b','/tmp/rm_ck.txt',
        f'http://localhost:5678/rest/workflows/{wf_id}'],
        capture_output=True, text=True, timeout=15)
    wf = json.loads(r.stdout).get('data', {})
    nodes = wf.get('nodes', [])
    
    changed = False
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        url = params.get('url', '')
        
        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url.lower():
            jb = str(params.get('jsonBody', '')).strip()
            clean = jb[1:].strip() if jb.startswith('=') else jb
            
            try:
                body = json.loads(clean) if clean else {}
                model = body.get('model', '')
                
                print(f"  [{wf_name}] '{name}': model={model!r}")
                
                # Заменяем устаревшую модель
                if 'gemini' in model or 'flash' in model or model != 'anthropic/claude-sonnet-4-5':
                    old_model = model
                    body['model'] = 'anthropic/claude-sonnet-4-5'
                    body['max_tokens'] = 2048
                    
                    # Убеждаемся что промпт правильный
                    for msg in body.get('messages', []):
                        if msg.get('role') == 'system' and len(msg.get('content','')) < 50:
                            msg['content'] = (
                                "Ты - эксперт по коммерческой недвижимости Москвы. "
                                "Напиши развёрнутый пост для Telegram канала Grandvest. "
                                "🏢 [ЗАГОЛОВОК]\n\n[ФАКТЫ]\n\n[КОНТЕКСТ]\n\n[ВЛИЯНИЕ]\n\n"
                                "💼 Комментарий Грандвест:\n💡 Совет:\n"
                                "👉 @Grandvest_bot\n#коммерческаянедвижимость #москва\n"
                                "ТРЕБОВАНИЯ: 900-1200 символов."
                            )
                    
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    
                    # Убеждаемся что Body Type = JSON, не Raw
                    params['specifyBody'] = 'json'
                    params['bodyContentType'] = 'json'
                    params.pop('rawBody', None)
                    
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': {old_model!r} → claude-sonnet-4-5")
                    print(f"    FIXED model!")
                    
            except json.JSONDecodeError as e:
                print(f"  [{wf_name}] '{name}': JSON error: {e}")
                # Проверяем rawBody
                rb = str(params.get('rawBody', params.get('body', ''))).strip()
                if rb:
                    clean_rb = rb[1:].strip() if rb.startswith('=') else rb
                    try:
                        body = json.loads(clean_rb)
                        model = body.get('model', '')
                        print(f"    rawBody model: {model!r}")
                        if model != 'anthropic/claude-sonnet-4-5' or body.get('max_tokens',0) < 2048:
                            body['model'] = 'anthropic/claude-sonnet-4-5'
                            body['max_tokens'] = 2048
                            params['specifyBody'] = 'json'
                            params['bodyContentType'] = 'json'
                            params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                            params.pop('rawBody', None)
                            params.pop('body', None)
                            n['parameters'] = params
                            changed = True
                            fixes.append(f"[{wf_name}] '{name}': rawBody fixed, model→claude-sonnet-4-5")
                    except:
                        pass
    
    if changed:
        print(f"  Saving {wf_name}...")
        result = n8n_put(wf_id, wf)
        saved = len(result.get('nodes', []))
        print(f"  Saved! {saved} nodes")

print(f"\nFixes: {fixes}")

if fixes:
    tg("✅ <b>RSS Fix применён:</b>\n" + '\n'.join(f"• {f}" for f in fixes) +
       "\n\nМодель исправлена: gemini-flash → claude-sonnet-4-5\nBody Type: Raw → JSON")
else:
    tg("ℹ️ RSS: все модели уже правильные")
PYEOF
