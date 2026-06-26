#!/bin/bash
BOT="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT="5340000158"

python3 << 'PYEOF'
import sqlite3, json, urllib.request, urllib.parse, subprocess

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
nodes = json.loads(cur.fetchone()[0])
conn.close()

# Деdup file
try:
    with open('/data/published_titles.json') as f:
        dedup = json.load(f)
    dedup_count = len(dedup)
    dedup_sample = dedup[-3:] if dedup else []
except:
    dedup_count = -1
    dedup_sample = []

report = [f'<b>Парсер Telegram - все узлы:</b>']
report.append(f'Dedup file: {dedup_count} items')
if dedup_sample:
    report.append(f'Last entries: {dedup_sample}')

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','').split('.')[-1]
    params = n.get('parameters',{})
    code = params.get('jsCode', params.get('code',''))
    url = params.get('url','')
    
    if code:
        line = f'\n<b>[{name}]</b>'
        # Для дедупликации - полный код
        if 'Дедупликац' in name or '2.' in name:
            line += f'\nCODE:\n<code>{code[:500]}</code>'
        # Для фильтра оценки
        elif 'фильтр' in name.lower() or 'оценк' in name.lower():
            line += f'\nCODE:\n<code>{code[:400]}</code>'
        # Для узла 9
        elif 'Отправка' in name or '9.' in name:
            # Показываем токен
            import re
            tokens = re.findall(r'ghp_[A-Za-z0-9]{10,}', code)
            line += f'\nTokens: {[t[:15] for t in tokens]}'
            line += f'\nhas grandvest-publisher: {"grandvest-publisher" in code}'
        else:
            line += f' [{ntype}] {url[:50]}'
        report.append(line)

msg = '\n'.join(report)
print(msg)
tg(msg)
PYEOF
