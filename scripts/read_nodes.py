import sqlite3, json, urllib.request, urllib.parse, http.cookiejar, os, time

DB = "/opt/n8n/n8n_data/database.sqlite"
RSS_WF = "SIPnV2mqmgMqUkLb"
try: BOT = open("/tmp/.tb").read().strip()
except: BOT = ""
CHAT = "5340000158"

def tg(msg):
    if not BOT: print(msg[:300]); return
    d = urllib.parse.urlencode({"chat_id":CHAT,"text":msg[:4096],"parse_mode":"HTML"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(
        "https://api.telegram.org/bot"+BOT+"/sendMessage",data=d,method="POST"),timeout=15)
    except Exception as e: print("TG:",e)

# Маппинг переименований
RENAMES = {
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
    tg("ERROR: RSS workflow not found!")
    exit(1)

wf_id, wf_name, nodes_raw, conns_raw = row
nodes = json.loads(nodes_raw)
conns = json.loads(conns_raw) if conns_raw else {}

renamed = []
# Создаём маппинг старых имён на новые
old_to_new = {}

for n in nodes:
    old_name = n.get("name", "")
    if old_name in RENAMES:
        new_name = RENAMES[old_name]
        old_to_new[old_name] = new_name
        n["name"] = new_name
        renamed.append(old_name + " → " + new_name)
        print("Renamed: " + old_name + " → " + new_name)

# Обновляем connections — заменяем старые имена на новые
new_conns = {}
for src_name, src_data in conns.items():
    new_src = old_to_new.get(src_name, src_name)
    new_outputs = {}
    if isinstance(src_data, dict):
        for output_type, outputs in src_data.items():
            if isinstance(outputs, list):
                new_output_list = []
                for output_list in outputs:
                    if isinstance(output_list, list):
                        new_items = []
                        for conn in output_list:
                            if isinstance(conn, dict) and "node" in conn:
                                conn["node"] = old_to_new.get(conn["node"], conn["node"])
                            new_items.append(conn)
                        new_output_list.append(new_items)
                    else:
                        new_output_list.append(output_list)
                new_outputs[output_type] = new_output_list
            else:
                new_outputs[output_type] = outputs
    new_conns[new_src] = new_outputs

cur.execute(
    "UPDATE workflow_entity SET nodes=?, connections=? WHERE id=?",
    (json.dumps(nodes, ensure_ascii=False),
     json.dumps(new_conns, ensure_ascii=False),
     wf_id)
)
conn.commit()
conn.close()
print("Saved " + str(len(renamed)) + " renames")

# Перезагружаем workflow через API
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    opener.open(urllib.request.Request(
        "http://localhost:5678/rest/workflows/"+RSS_WF+"/deactivate",
        data=b"{}", headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    time.sleep(2)
    opener.open(urllib.request.Request(
        "http://localhost:5678/rest/workflows/"+RSS_WF+"/activate",
        data=b"{}", headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    print("Workflow reloaded")
except Exception as e:
    print("API err:", str(e)[:80])

tg(
    "<b>RSS УЗЛЫ ПЕРЕИМЕНОВАНЫ</b>\n\n" +
    "\n".join("• " + r for r in renamed) +
    "\n\nОбнови страницу n8n — увидишь новые имена!"
)
print("DONE")
