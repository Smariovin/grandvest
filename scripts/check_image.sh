#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

curl -s -c /tmp/ci_ck.txt -X POST http://localhost:5678/rest/login \
  -H 'Content-Type: application/json' \
  -d '{"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}' > /dev/null

# Читаем последний успешный execution ID#1533
curl -s -b /tmp/ci_ck.txt 'http://localhost:5678/rest/executions/1533' | \
python3 -c "
import sys, json, urllib.request, urllib.parse

BOT='8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT='5340000158'

def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000],'parse_mode':'HTML'}).encode(),
        method='POST'), timeout=10)

raw = sys.stdin.read()
try:
    d = json.loads(raw)
    ex = d.get('data', d)
    result = ex.get('data', {}).get('resultData', {})
    run_data = result.get('runData', {})
    
    report = ['<b>Execution #1533 детали:</b>']
    
    for node_name, node_runs in run_data.items():
        for nr in (node_runs or []):
            es = nr.get('executionStatus', '?')
            out = nr.get('data', {}).get('main', [[]])
            cnt = len(out[0]) if out and out[0] else 0
            
            icon = '✅' if es == 'success' else '❌'
            line = f'{icon} {node_name}: {cnt} items'
            
            # Для ключевых узлов показываем данные
            if cnt > 0 and out[0]:
                first = out[0][0].get('json', {})
                if 'tg_post' in first:
                    post = first.get('tg_post', '')
                    img = first.get('image_url', first.get('image_prompt', ''))
                    line += f'\n   tg_post({len(post)} chars): {post[:80]!r}'
                    line += f'\n   image_url: {str(img)[:80]!r}'
                elif 'images' in first:
                    imgs = first.get('images', [])
                    line += f'\n   images: {imgs[0].get(\"url\",\"?\")[:80] if imgs else \"empty\"}'
                elif 'url' in first:
                    line += f'\n   url: {str(first.get(\"url\",\"\"))[:80]}'
            
            report.append(line)
    
    tg('\n'.join(report))
    print('\n'.join(report))
except Exception as e:
    tg(f'Parse error: {e}')
    print(f'Error: {e}: {raw[:200]}')
" 2>&1
