#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/dl_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Берём последние 3 execution и читаем ВСЕ узлы с ошибками
curl -s -b /tmp/dl_ck.txt 'http://localhost:5678/rest/executions?limit=3' | python3 << 'PYEOF'
import sys, json, subprocess, urllib.request, urllib.parse

BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'
    }).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

d = json.load(sys.stdin)
items = d.get('data', {})
if isinstance(items, dict): items = items.get('results', [])

for ex in items[:3]:
    ex_id = ex.get('id','?')
    wf = ex.get('workflowData',{}).get('name','?')
    status = ex.get('status','?')
    t = str(ex.get('startedAt','?'))[11:16]
    
    if status != 'error' and status != 'failed':
        continue  # Смотрим только ошибки
    
    # Получаем детали execution
    r = subprocess.run(['curl','-s','-b','/tmp/dl_ck.txt',
        f'http://localhost:5678/rest/executions/{ex_id}'],
        capture_output=True, text=True, timeout=15)
    
    try:
        ex_data = json.loads(r.stdout).get('data', {})
        run_data = ex_data.get('data',{}).get('resultData',{}).get('runData',{})
        
        lines = [f'<b>❌ {wf} [{t}]</b>\n']
        
        for node_name, node_runs in run_data.items():
            for nr in (node_runs or []):
                es = nr.get('executionStatus','?')
                err = nr.get('error')
                out = nr.get('data',{}).get('main',[[]])
                cnt = len(out[0]) if out and out[0] else 0
                
                icon = '✅' if es == 'success' else '❌' if err else '⚪'
                line = f'{icon} <b>{node_name}</b>: {cnt} items'
                
                if err:
                    line += f'\n   ❗ {str(err.get("message","?"))[:120]}'
                
                if es == 'success' and cnt == 0:
                    # Узел прошёл но вернул 0 — это фильтр заблокировал
                    line += ' ← ЗАБЛОКИРОВАНО'
                    
                    # Смотрим что было на входе у фильтра
                    inp = nr.get('inputOverride',{})
                    if inp:
                        line += f'\n   Вход: {str(inp)[:100]}'
                
                lines.append(line)
        
        tg('\n'.join(lines))
    except Exception as e:
        tg(f'Parse error {ex_id}: {e}')
PYEOF
