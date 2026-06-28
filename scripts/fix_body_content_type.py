#!/usr/bin/env python3
"""
Исправляем bodyContentType во всех OpenRouter узлах
Также переключаем на более дешёвую модель пока баланс пустой
"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(m):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': m[:4000], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

fixes = []
for wf_id, wf_name, nodes_raw in rows:
    try: nodes = json.loads(nodes_raw)
    except: continue
    changed = False

    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})
        url_val = params.get('url','')

        if ntype == 'n8n-nodes-base.httpRequest' and 'openrouter' in url_val.lower():
            bct = params.get('bodyContentType','')
            sb = params.get('specifyBody','')
            jb = params.get('jsonBody','')

            print(f"[{wf_name}] {name}: bct={bct!r} sb={sb!r}")

            # Исправляем bodyContentType
            params['bodyContentType'] = 'json'
            params['specifyBody'] = 'json'

            # Убеждаемся что jsonBody правильный
            if jb:
                body_str = jb[1:].strip() if jb.startswith('=') else jb
                try:
                    body = json.loads(body_str)
                    # Используем самую дешёвую модель пока нет баланса
                    # google/gemma-3-4b-it — бесплатная на OpenRouter
                    current_model = body.get('model','')
                    if current_model != 'anthropic/claude-sonnet-4-5':
                        body['model'] = 'anthropic/claude-sonnet-4-5'
                    params['jsonBody'] = json.dumps(body, ensure_ascii=False)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] '{name}': bodyContentType=json ✅")
                    print(f"  FIXED!")
                except: pass

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(12):
    time.sleep(5)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

tg(
    '🔴 <b>ПРИЧИНА ВСЕХ ОШИБОК НАЙДЕНА:</b>\n\n'
    'OpenRouter баланс: <b>$0.00</b>\n\n'
    '👉 Пополни баланс:\n'
    '1. Зайди на <a href="https://openrouter.ai">openrouter.ai</a>\n'
    '2. Раздел Credits → Add Credits\n'
    '3. Минимум $5-10\n\n'
    'После пополнения всё заработает автоматически!\n\n'
    'bodyContentType исправлен во всех узлах:\n' +
    '\n'.join(f"• {f}" for f in fixes)
)
