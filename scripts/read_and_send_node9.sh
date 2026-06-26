#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"
WORKING_PAT="${WORKING_PAT}"

python3 << PYEOF
import sqlite3, json, re, os, urllib.request, urllib.parse, subprocess

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'
PAT = os.environ.get('WORKING_PAT','')

def tg(m):
    urllib.request.urlopen(urllib.request.Request(
        f'https://api.telegram.org/bot{BOT}/sendMessage',
        data=urllib.parse.urlencode({'chat_id':CHAT,'text':m[:4000]}).encode(),
        method='POST'),timeout=10)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
nodes = json.loads(cur.fetchone()[0])

report = ['<b>Текущее состояние узлов:</b>']
node9_code = ''

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','').split('.')[-1]
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    url = params.get('url','')
    jb = str(params.get('jsonBody','')).strip()

    if code and len(code) > 20:
        tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
        has_pub = 'grandvest-publisher' in code
        
        if tokens or has_pub:
            report.append(f'\n<b>{name}</b>')
            report.append(f'tokens: {[t[:12] for t in tokens]}')
            report.append(f'has_publisher: {has_pub}')
        
        if 'Отправка' in name or '9.' in name:
            node9_code = code
            report.append(f'CODE:\n{code[:400]}')
    
    if 'openrouter' in url.lower():
        try:
            clean = jb[1:] if jb.startswith('=') else jb
            body = json.loads(clean) if clean else {}
            mt = body.get('max_tokens',0)
            report.append(f'\n<b>{name}</b> max_tokens={mt}')
        except:
            report.append(f'\n<b>{name}</b> jsonBody INVALID')
    
    if 'фильтр' in name.lower():
        score_line = [l for l in code.split('\n') if 'score >=' in l or 'score >' in l]
        report.append(f'\n<b>{name}</b> threshold: {score_line}')

conn.close()
tg('\n'.join(report))

# Тест dispatch напрямую с нашим PAT
print(f'Testing dispatch with PAT {PAT[:15]}...')
try:
    payload = json.dumps({'ref':'main','inputs':{'message':'Тест прямой публикации','image_url':''}}).encode()
    req = urllib.request.Request(
        'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',
        data=payload,
        headers={'Authorization':f'token {PAT}','Content-Type':'application/json','Accept':'application/vnd.github+json'}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        tg(f'✅ Direct dispatch OK! Status: {r.status}\nPAT {PAT[:15]}... работает!')
        print(f'Dispatch OK: {r.status}')
except Exception as e:
    tg(f'❌ Direct dispatch FAIL: {e}\nPAT: {PAT[:15]}...')
    print(f'Dispatch FAIL: {e}')
PYEOF
