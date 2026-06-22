import sqlite3, json

DB = "/opt/n8n/n8n_data/database.sqlite"
con = sqlite3.connect(DB)
cur = con.cursor()

RENAMES = {
    "Code in JavaScript": "1. Парсинг HTML Telegram",
    "Code in JavaScript1": "2. Дедупликация входящих",
    "Code in JavaScript2": "6. Извлечение текста поста",
    "Code in JavaScript3": "9. Отправка в Telegram",
    "Code in JavaScript4": "10. Запись в дедупликацию",
    "Code \u2014 \u0438\u0437\u0432\u043b\u0435\u0447\u0435\u043d\u0438\u0435 \u043f\u043e\u0441\u0442\u0430": "8. \u041f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430 \u0434\u0430\u043d\u043d\u044b\u0445 \u043f\u043e\u0441\u0442\u0430"
}

all_wf = cur.execute("SELECT id,name,nodes,connections FROM workflow_entity").fetchall()

for r in all_wf:
    if "Парсер" not in r[1] and "Telegram" not in r[1]:
        continue

    nodes = json.loads(r[2])
    conns = json.loads(r[3])
    changed = False

    for node in nodes:
        old = node["name"]
        if old in RENAMES:
            new = RENAMES[old]
            print("Renaming: " + old + " -> " + new)
            node["name"] = new
            if old in conns:
                conns[new] = conns.pop(old)
            for src in list(conns.keys()):
                for branch in conns[src].get("main", []):
                    for conn in branch:
                        if conn.get("node") == old:
                            conn["node"] = new
            changed = True

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?,connections=? WHERE id=?",
            (json.dumps(nodes, ensure_ascii=False),
             json.dumps(conns, ensure_ascii=False), r[0]))
        print("Saved: " + r[1])

con.commit()
con.close()
print("DONE! Run: docker restart n8n")
