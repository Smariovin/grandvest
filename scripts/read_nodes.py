#!/usr/bin/env python3
"""Переименовываем узлы RSS workflow"""
import sqlite3, json, urllib.request, urllib.parse, http.cookiejar, os, time

DB = "/opt/n8n/n8n_data/database.sqlite"
N8N = "http://localhost:5678"
RSS_WF = "SIPnV2mqmgMqUkLb"
try:
    BOT = open("/tmp/.tb").read().strip()
except:
    BOT = ""
CHAT = "5340000158"

def tg(msg):
    if not BOT: print(msg[:300]); return
    d = urllib.parse.urlencode({"chat_id": CHAT, "text": msg[:4096], "parse_mode": "HTML"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(
        "https://api.telegram.org/bot" + BOT + "/sendMessage", data=d, method="POST"), timeout=15)
    except Exception as e: print("TG:", e)

# Карта переименований: старое -> новое
RENAME_MAP = {
    "HTTP Request":   "Google News: ком.недвижимость",
    "HTTP Request1":  "Google News: аренда офисов",
    "HTTP Request2":  "Google News: склады",
    "HTTP Request3":  "Google News: торговая недвижимость",
    "HTTP Request4":  "Google News: девелопмент",
    "HTTP Request5":  "Google News: инвестиции",
    "HTTP Request10": "Ведомости RSS",
    "Code in JavaScript":  "Парсинг XML",
    "HTTP Request6":  "Claude — оценка новости",
    "Code in JavaScript1": "Фильтр оценки",
    "Code in JavaScript3": "Дедупликация",
    "HTTP Request7":  "Claude — генерация поста",
    "Code in JavaScript2": "Извлечение поста",
    "HTTP Request9":  "fal.ai — картинка",
    "HTTP Request8":  "Отправка в Publisher",
    "Code in JavaScript4": "Запись в дедупликацию",
    "Code in JavaScript5": "Отчёт RSS",
}

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes, connections FROM workflow_entity WHERE id=?", (RSS_WF,))
row = cur.fetchone()
if not row:
    print("NOT FOUND"); exit(1)

wf_id, wf_name, nodes_raw, conns_raw = row
nodes = json.loads(nodes_raw)
conns = json.loads(conns_raw) if conns_raw else {}

renamed = []
old_to_new = {}

for n in nodes:
    old_name = n.get("name", "")
    if old_name in RENAME_MAP:
        new_name = RENAME_MAP[old_name]
        old_to_new[old_name] = new_name
        n["name"] = new_name
        renamed.append(old_name + " -> " + new_name)
        print("Renamed: " + old_name + " -> " + new_name)

# Обновляем connections
new_conns = {}
for src, data in conns.items():
    new_src = old_to_new.get(src, src)
    new_data = {}
    for out_type, outputs in data.items():
        new_outputs = []
        for output_list in outputs:
            new_output_list = []
            for conn in output_list:
                new_conn = dict(conn)
                if conn.get("node") in old_to_new:
                    new_conn["node"] = old_to_new[conn["node"]]
                new_output_list.append(new_conn)
            new_outputs.append(new_output_list)
        new_data[out_type] = new_outputs
    new_conns[new_src] = new_data

cur.execute("UPDATE workflow_entity SET nodes=?, connections=? WHERE id=?",
           (json.dumps(nodes, ensure_ascii=False),
            json.dumps(new_conns, ensure_ascii=False),
            wf_id))
conn.commit()
conn.close()
print(f"Done. Renamed {len(renamed)} nodes")

# Перезагружаем через API
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId": "admin@grandvest.ru", "password": "Grandvest2026!"}).encode()
try:
    opener.open(urllib.request.Request(N8N + "/rest/login",
        data=ld, headers={"Content-Type": "application/json"}, method="POST"), timeout=10)
    opener.open(urllib.request.Request(
        N8N + "/rest/workflows/" + RSS_WF + "/deactivate",
        data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=10)
    time.sleep(2)
    opener.open(urllib.request.Request(
        N8N + "/rest/workflows/" + RSS_WF + "/activate",
        data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=10)
    print("Workflow reloaded")
except Exception as e:
    print("Reload err:", str(e)[:80])

tg(
    "<b>RSS NODES RENAMED</b>\n\n" +
    "\n".join("• " + r for r in renamed) +
    "\n\nОбновите страницу n8n — увидите новые названия!"
)
print("DONE")
