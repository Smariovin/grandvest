#!/usr/bin/env python3
"""
Диагностика: смотрим connections (связи) между узлами
и проверяем параметры HTTP Request генерации
"""
import sqlite3, json, urllib.request, urllib.parse, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
CHAT = '5340000158'

def tg(msg):
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4000]}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
nodes_raw, connections_raw = row
nodes = json.loads(nodes_raw)
connections = json.loads(connections_raw)

# Показываем связи
report = ["=== CONNECTIONS ==="]
for from_node, conn_data in connections.items():
    for conn_type, targets in conn_data.items():
        for target_list in targets:
            for target in target_list:
                to_node = target.get('node','?')
                report.append(f"  {from_node} -> {to_node}")

print('\n'.join(report))

# Показываем параметры узла генерации ПОЛНОСТЬЮ
report2 = ["\n=== HTTP Request — генерация поста (FULL PARAMS) ==="]
for n in nodes:
    if n.get('name') == 'HTTP Request — генерация поста':
        params = n.get('parameters', {})
        report2.append(f"Method: {params.get('method','?')}")
        report2.append(f"URL: {params.get('url','?')}")
        
        # jsonBody
        jb = params.get('jsonBody', '')
        report2.append(f"jsonBody type: {type(jb).__name__}")
        report2.append(f"jsonBody ({len(str(jb))} chars):")
        
        if isinstance(jb, str):
            try:
                jb_parsed = json.loads(jb)
                report2.append(f"  model: {jb_parsed.get('model','?')}")
                report2.append(f"  max_tokens: {jb_parsed.get('max_tokens','?')}")
                msgs = jb_parsed.get('messages', [])
                report2.append(f"  messages: {len(msgs)}")
                for msg in msgs:
                    role = msg.get('role','?')
                    content = msg.get('content','')
                    report2.append(f"    [{role}]: {content[:100]!r}")
            except:
                report2.append(f"  RAW: {jb[:300]}")
        else:
            report2.append(f"  {json.dumps(jb, ensure_ascii=False)[:300]}")
        
        # Проверяем specifyBody
        report2.append(f"specifyBody: {params.get('specifyBody','?')}")
        report2.append(f"bodyContentType: {params.get('bodyContentType','?')}")
        report2.append(f"sendBody: {params.get('sendBody','?')}")
        
        # Все ключи параметров
        report2.append(f"All param keys: {list(params.keys())}")
        break

full_report = '\n'.join(report) + '\n' + '\n'.join(report2)
print('\n'.join(report2))
tg(full_report[:4000])
conn.close()
