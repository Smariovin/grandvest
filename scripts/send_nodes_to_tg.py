#!/usr/bin/env python3
import sqlite3, json, urllib.request, urllib.parse

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except Exception as e:
        print(f'TG error: {e}')

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
conn.close()

nodes = json.loads(row[0])
msg = '<b>Nodes in Парсер Telegram:</b>\n\n'

for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code', ''))
    
    if code:
        first_line = code.split('\n')[0][:80]
        msg += f'<b>{name}</b>\n'
        msg += f'type: {ntype.split(".")[-1]}\n'
        msg += f'code ({len(code)}): <code>{first_line}</code>\n\n'

tg(msg)
print('Sent to Telegram!')
print(msg)
