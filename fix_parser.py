import sqlite3, json, copy

DB = "/opt/n8n/n8n_data/database.sqlite"
RSS_ID = "SIPnV2mqmgMqUkLb"
PARSER_ID = "F24jvKiXJIs4wRiZ"

COPY_NODES = [
    "HTTP Request — генерация поста",
    "Code — извлечение поста",
    "HTTP Request — fal.ai",
    "HTTP Request — Telegram",
    "Code in JavaScript4"
]

con = sqlite3.connect(DB)
cur = con.cursor()

def get_wf(wid):
    row = cur.execute("SELECT id,name,nodes,connections FROM workflow_entity WHERE id=?", (wid,)).fetchone()
    if not row:
        raise SystemExit("Not found: " + wid)
    return {"id":row[0],"name":row[1],"nodes":json.loads(row[2]),"connections":json.loads(row[3])}

print("Reading RSS workflow...")
rss = get_wf(RSS_ID)
rss_nodes = {n["name"]:n for n in rss["nodes"]}
print("RSS nodes: " + str(list(rss_nodes.keys())))

print("Reading Parser workflow...")
parser = get_wf(PARSER_ID)
parser_nodes = {n["name"]:n for n in parser["nodes"]}
print("Parser nodes: " + str(list(parser_nodes.keys())))

anchor = parser_nodes.get("Claude — оценка поста") or parser_nodes.get("Code — фильтр оценки")
if not anchor:
    raise SystemExit("Anchor not found! Available: " + str(list(parser_nodes.keys())))
print("Anchor: " + anchor["name"])

found = [n for n in COPY_NODES if n in rss_nodes]
print("Found " + str(len(found)) + " nodes: " + str(found))
if not found:
    raise SystemExit("No nodes found! RSS has: " + str(list(rss_nodes.keys())))

parser["nodes"] = [n for n in parser["nodes"] if n["name"] not in set(COPY_NODES)]

ax = anchor["position"][0]
ay = anchor["position"][1]
new_nodes = []
for i,name in enumerate(COPY_NODES):
    if name not in rss_nodes:
        continue
    node = copy.deepcopy(rss_nodes[name])
    node["position"] = [ax+250*(i+1), ay]
    new_nodes.append(node)
    print("Adding: " + name)

parser["nodes"].extend(new_nodes)

conns = parser["connections"]
anchor_name = anchor["name"]
conns[anchor_name] = {"main":[[]]}

prev = anchor_name
for node in new_nodes:
    nn = node["name"]
    if prev not in conns:
        conns[prev] = {"main":[[]]}
    conns[prev]["main"][0] = [{"node":nn,"type":"main","index":0}]
    prev = nn

cur.execute("UPDATE workflow_entity SET nodes=?,connections=? WHERE id=?",
    (json.dumps(parser["nodes"],ensure_ascii=False),
     json.dumps(conns,ensure_ascii=False), PARSER_ID))
con.commit()
con.close()
print("DONE! Now run: docker restart n8n")
