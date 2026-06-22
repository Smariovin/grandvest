import sqlite3, json

DB = "/opt/n8n/n8n_data/database.sqlite"
con = sqlite3.connect(DB)
cur = con.cursor()

wf = cur.execute('SELECT id,nodes FROM workflow_entity WHERE name LIKE "%Парсер%"').fetchone()
nodes = json.loads(wf[1])

FIXES = {
    "Code in JavaScript1": "2. Дедупликация входящих",
    "Code in JavaScript2": "6. Извлечение текста поста",
    "Code in JavaScript3": "9. Отправка в Telegram",
    "Code in JavaScript4": "10. Запись в дедупликацию",
    "Code - фильтр оценки": "Code \u2014 фильтр оценки",
    "HTTP Request - fal.ai": "HTTP Request \u2014 fal.ai",
    "If": "8. Подготовка данных поста"
}

for n in nodes:
    code = n.get("parameters", {}).get("jsCode", "")
    if not code:
        continue
    old = code
    for old_name, new_name in FIXES.items():
        code = code.replace("$('" + old_name + "')", "('" + new_name + "')")
        code = code.replace('("' + old_name + '")', '("' + new_name + '")')
        code = code.replace("$node['" + old_name + "']", "$node['" + new_name + "']")
        code = code.replace('$node["' + old_name + '"]', '$node["' + new_name + '"]')
    if code != old:
        n["parameters"]["jsCode"] = code
        print("Fixed: " + n["name"])

cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
    (json.dumps(nodes, ensure_ascii=False), wf[0]))
con.commit()
con.close()
print("DONE")
