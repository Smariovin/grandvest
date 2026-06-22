import sqlite3, json, copy

DB = "/opt/n8n/n8n_data/database.sqlite"

con = sqlite3.connect(DB)
cur = con.cursor()

all_wf = cur.execute("SELECT id,name,nodes,connections FROM workflow_entity").fetchall()
print("All workflows:")
for r in all_wf:
    print("  " + r[0] + " | " + r[1])

rss = None
parser = None
for r in all_wf:
    if "RSS" in r[1] or "Сбор" in r[1]:
        rss = {"id":r[0],"name":r[1],"nodes":json.loads(r[2]),"connections":json.loads(r[3])}
    if "Парсер" in r[1] or "Parser" in r[1] or "Telegram" in r[1]:
        parser = {"id":r[0],"name":r[1],"nodes":json.loads(r[2]),"connections":json.loads(r[3])}

if not rss:
    raise SystemExit("RSS workflow not found!")
if not parser:
    raise SystemExit("Parser workflow not found!")

print("RSS: " + rss["name"])
print("Parser: " + parser["name"])

rss_nodes = {n["name"]:n for n in rss["nodes"]}
print("RSS nodes: " + str(list(rss_nodes.keys())))

parser_nodes = {n["name"]:n for n in parser["nodes"]}
print("Parser nodes: " + str(list(parser_nodes.keys())))

COPY_NODES = []
for name in rss_nodes:
    if any(x in name for x in ["генерация", "извлечение", "fal.ai", "Telegram", "JavaScript4", "JavaScript2"]):
        COPY_NODES.append(name)
        print("Will copy: " + name)

anchor = None
for key in ["Claude", "оценка", "фильтр"]:
    for name, node in parser_nodes.items():
        if key in name:
            anchor = node
            break
    if anchor:
        break

if not anchor:
    raise SystemExit("Anchor not found! Parser nodes: " + str(list(parser_nodes.keys())))

anchor_name = anchor["name"]
print("Anchor: " + anchor_name)

parser["nodes"] = [n for n in parser["nodes"] if n["name"] not in set(COPY_NODES)]

ax = anchor["position"][0]
ay = anchor["position"][1]
new_nodes = []
for i, name in enumerate(COPY_NODES):
    node = copy.deepcopy(rss_nodes[name])
    node["position"] = [ax + 250*(i+1), ay]
    new_nodes.append(node)
    print("Adding: " + name)

parser["nodes"].extend(new_nodes)

conns = parser["connections"]
conns[anchor_name] = {"main":[[]]}

prev = anchor_name
for node in new_nodes:
    nn = node["name"]
    if prev not in conns:
        conns[prev] = {"main":[[]]}
    conns[prev]["main"][0] = [{"node":nn,"type":"main","index":0}]
    prev = nn

cur.execute("UPDATE workflow_entity SET nodes=?,connections=? WHERE id=?",
    (json.dumps(parser["nodes"], ensure_ascii=False),
     json.dumps(conns, ensure_ascii=False), parser["id"]))
con.commit()
con.close()
print("DONE! Run: docker restart n8n")
