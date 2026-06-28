#!/usr/bin/env python3
"""Удаляем узел 'Отчёт RSS парсинга' из RSS workflow"""
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')

def tg(msg):
    if not BOT: print("TG:", msg); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== DELETE RSS REPORT NODE ===")

subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes, connections FROM workflow_entity")
all_wf = cur.fetchall()

rss_wf = None
for wf_id, wf_name, nodes_raw, conns_raw in all_wf:
    if 'RSS' in wf_name or 'Сбор новостей' in wf_name:
        rss_wf = (wf_id, wf_name, nodes_raw, conns_raw)
        break

if not rss_wf:
    tg("ERROR: RSS workflow not found!")
    conn.close()
    exit(1)

wf_id, wf_name, nodes_raw, conns_raw = rss_wf
nodes = json.loads(nodes_raw)
conns = json.loads(conns_raw) if conns_raw else {}

print(f"Before: {len(nodes)} nodes")

# Находим узлы для удаления
nodes_to_delete = []
for n in nodes:
    name = n.get('name','')
    if 'Отчёт RSS' in name or 'RSS Отчёт' in name or 'отчёт rss' in name.lower():
        nodes_to_delete.append(name)
        print(f"  Will delete: [{name}]")

if not nodes_to_delete:
    print("No report nodes found!")
    tg("Узлы 'Отчёт RSS' не найдены в workflow")
    conn.close()
    exit(0)

# Удаляем узлы
nodes = [n for n in nodes if n.get('name','') not in nodes_to_delete]
print(f"After: {len(nodes)} nodes")

# Удаляем из connections
for node_name in nodes_to_delete:
    conns.pop(node_name, None)
    # Удаляем ссылки на этот узел из других connections
    for src_name, src_data in conns.items():
        if isinstance(src_data, dict):
            for output_type, outputs in src_data.items():
                if isinstance(outputs, list):
                    for i, output_list in enumerate(outputs):
                        if isinstance(output_list, list):
                            outputs[i] = [
                                conn for conn in output_list
                                if conn.get('node') not in nodes_to_delete
                            ]

# Сохраняем
cur.execute(
    "UPDATE workflow_entity SET nodes=?, connections=?, active=1 WHERE id=?",
    (json.dumps(nodes, ensure_ascii=False),
     json.dumps(conns, ensure_ascii=False),
     wf_id)
)
conn.commit()
conn.close()

# Перезапуск n8n
subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

deleted_str = ", ".join(nodes_to_delete)
tg(
    "🗑 <b>Узлы удалены из RSS workflow</b>\n\n"
    "Удалено: " + deleted_str + "\n"
    "Осталось узлов: " + str(len(nodes)) + "\n\n"
    "n8n перезапущен. Схема стала чище ✅"
)
print("DONE. Deleted: " + str(nodes_to_delete))
