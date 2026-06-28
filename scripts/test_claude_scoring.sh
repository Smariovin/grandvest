#!/bin/bash
# Тестируем узел Claude напрямую через OpenRouter

curl -s -c /tmp/tcs_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

python3 << 'PYEOF'
import subprocess, json, re, urllib.request, urllib.parse, sqlite3

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

# Читаем текущий узел из n8n
r = subprocess.run(['curl','-s','-b','/tmp/tcs_ck.txt',
    'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ'],
    capture_output=True, text=True, timeout=15)
wf = json.loads(r.stdout).get('data', {})
nodes = wf.get('nodes', [])

# OR ключ из SQLite
db = sqlite3.connect('/opt/n8n/n8n_data/database.sqlite')
cur = db.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
or_key = ''
if row:
    keys = re.findall(r'sk-or-v1-[a-f0-9]{60,}', row[0])
    if keys: or_key = keys[0]
db.close()
print(f"OR key: {or_key[:20]}...")

report = ['<b>Диагностика узлов Парсер Telegram:</b>\n']

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    url_val = params.get('url','')
    
    if 'Claude' in name and 'оценка' in name.lower():
        jb = str(params.get('jsonBody','')).strip()
        rb = str(params.get('rawBody','')).strip()
        specify = params.get('specifyBody','?')
        bct = params.get('bodyContentType','?')
        
        report.append(f'<b>Claude — оценка поста:</b>')
        report.append(f'specifyBody: {specify!r}')
        report.append(f'bodyContentType: {bct!r}')
        report.append(f'jsonBody[:100]: {jb[:100]!r}')
        report.append(f'rawBody[:60]: {rb[:60]!r}')
        
        # Проверяем что тело валидное
        body_str = jb[1:].strip() if jb.startswith('=') else jb
        if not body_str:
            body_str = rb[1:].strip() if rb.startswith('=') else rb
        
        try:
            body = json.loads(body_str)
            model = body.get('model','?')
            mt = body.get('max_tokens','?')
            msgs = len(body.get('messages',[]))
            report.append(f'✅ JSON валидный: model={model} max_tokens={mt} messages={msgs}')
            
            # Тест реального запроса к OpenRouter
            report.append('\n<b>Тест OpenRouter:</b>')
            test_body = {
                "model": "anthropic/claude-sonnet-4-5",
                "max_tokens": 50,
                "messages": [
                    {"role": "system", "content": "Ответь только: {\"score\": 8}"},
                    {"role": "user", "content": "Тест"}
                ]
            }
            req = urllib.request.Request(
                'https://openrouter.ai/api/v1/chat/completions',
                data=json.dumps(test_body).encode(),
                headers={
                    'Authorization': f'Bearer {or_key}',
                    'Content-Type': 'application/json',
                    'HTTP-Referer': 'https://grandvest.ru'
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                content = result.get('choices',[])[0].get('message',{}).get('content','?')
                report.append(f'✅ OpenRouter OK: {content[:50]}')
                
        except json.JSONDecodeError as e:
            report.append(f'❌ JSON невалидный: {e}')
            report.append(f'body_str: {body_str[:100]!r}')
        except urllib.request.HTTPError as e:
            err_body = e.read().decode()[:200]
            report.append(f'❌ OpenRouter {e.code}: {err_body}')
        except Exception as e:
            report.append(f'❌ Error: {e}')

tg('\n'.join(report))
print('\n'.join(report))
PYEOF
