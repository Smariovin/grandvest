import sqlite3, json

DB = "/opt/n8n/n8n_data/database.sqlite"
con = sqlite3.connect(DB)
cur = con.cursor()

all_wf = cur.execute("SELECT id,name,nodes,connections FROM workflow_entity").fetchall()
parser = None
for r in all_wf:
    if "Парсер" in r[1] or "Telegram" in r[1]:
        parser = {"id":r[0],"name":r[1],"nodes":json.loads(r[2]),"connections":json.loads(r[3])}

if not parser:
    raise SystemExit("Parser not found!")

nodes = {n["name"]:n for n in parser["nodes"]}
print("Current nodes: " + str(list(nodes.keys())))

ORDER = [
    "Webhook",
    "Code in JavaScript",
    "Code in JavaScript1",
    "Claude \u2014 \u043e\u0446\u0435\u043d\u043a\u0430 \u043f\u043e\u0441\u0442\u0430",
    "Code \u2014 \u0444\u0438\u043b\u044c\u0442\u0440 \u043e\u0446\u0435\u043d\u043a\u0438",
    "HTTP Request \u2014 \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f \u043f\u043e\u0441\u0442\u0430",
    "Code in JavaScript2",
    "HTTP Request \u2014 fal.ai",
    "Code \u2014 \u0438\u0437\u0432\u043b\u0435\u0447\u0435\u043d\u0438\u0435 \u043f\u043e\u0441\u0442\u0430",
    "Code in JavaScript4"
]

missing = [n for n in ORDER if n not in nodes]
if missing:
    print("Missing nodes: " + str(missing))

present = [n for n in ORDER if n in nodes]
print("Will chain: " + str(present))

for i, name in enumerate(present):
    nodes[name]["position"] = [40 + i * 160, 200]

new_conns = {}
for i in range(len(present) - 1):
    src = present[i]
    dst = present[i+1]
    new_conns[src] = {"main": [[{"node": dst, "type": "main", "index": 0}]]}

new_conns[present[-1]] = {"main": [[]]}

parser["connections"] = new_conns

cur.execute("UPDATE workflow_entity SET nodes=?,connections=? WHERE id=?",
    (json.dumps(parser["nodes"], ensure_ascii=False),
     json.dumps(new_conns, ensure_ascii=False), parser["id"]))
con.commit()
con.close()
print("DONE! Connections fixed.")
