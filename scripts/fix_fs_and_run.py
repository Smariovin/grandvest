#!/usr/bin/env python3
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time, http.cookiejar

DB = "/opt/n8n/n8n_data/database.sqlite"
BOT = os.environ.get("TG_BOT","")
CHAT = os.environ.get("TG_CHAT","5340000158")
RSS_WF_ID = "SIPnV2mqmgMqUkLb"

def tg(msg):
    if not BOT: print("TG:", msg[:300]); return
    url = "https://api.telegram.org/bot" + BOT + "/sendMessage"
    data = urllib.parse.urlencode({"chat_id":CHAT,"text":msg[:4096],"parse_mode":"HTML"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method="POST"),timeout=15)
    except Exception as e: print("TG err:", e)

DEDUP_CODE = (
    "const items = $input.all();\n"
    "const staticData = $getWorkflowStaticData(\"global\");\n"
    "if (!staticData.publishedTitles) staticData.publishedTitles = [];\n"
    "const published = staticData.publishedTitles;\n"
    "const unique = [];\n"
    "for (const item of items) {\n"
    "  const title = (item.json.title || item.json.text || \"\").trim().toLowerCase().substring(0, 80);\n"
    "  if (!title) continue;\n"
    "  const isDup = published.some(function(p) { return p.substring(0,80) === title; });\n"
    "  if (!isDup) unique.push(item);\n"
    "  else console.log(\"Dup skipped:\", title.substring(0,40));\n"
    "}\n"
    "if (staticData.publishedTitles.length > 500) {\n"
    "  staticData.publishedTitles = staticData.publishedTitles.slice(-300);\n"
    "}\n"
    "console.log(\"Dedup: in=\" + items.length + \" out=\" + unique.length);\n"
    "return unique.slice(0, 1);"
)

WRITE_DEDUP_CODE = (
    "const item = $input.first().json;\n"
    "const title = (item.title || item.text || item.tg_post || \"\").trim().toLowerCase().substring(0, 80);\n"
    "if (title) {\n"
    "  const staticData = $getWorkflowStaticData(\"global\");\n"
    "  if (!staticData.publishedTitles) staticData.publishedTitles = [];\n"
    "  if (!staticData.publishedTitles.includes(title)) {\n"
    "    staticData.publishedTitles.push(title);\n"
    "  }\n"
    "}\n"
    "return [$input.first()];"
)

print("=== FIX FS NODES ===")
subprocess.run(["docker","stop","n8n"], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id=?", (RSS_WF_ID,))
row = cur.fetchone()

if not row:
    tg("ERROR: RSS workflow not found!")
    conn.close(); exit(1)

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
fixes = []
changed = False

print("RSS: " + wf_name + " | nodes: " + str(len(nodes)))

for n in nodes:
    name = n.get("name","")
    ntype = n.get("type","")
    params = n.get("parameters",{})
    if ntype != "n8n-nodes-base.code": continue
    code = params.get("jsCode","")
    print("Code [" + name + "]: has_require=" + str("require(" in code))
    if "require(" in code and "fs" in code:
        print("  FIXING: " + name)
        if "writeFileSync" in code:
            params["jsCode"] = WRITE_DEDUP_CODE
            fixes.append("WRITE_DEDUP: " + name)
        else:
            params["jsCode"] = DEDUP_CODE
            fixes.append("DEDUP: " + name)
        n["parameters"] = params
        changed = True

# Принудительно фиксируем по именам если не нашли через require
if not changed:
    print("require(fs) not found by scan - forcing by name...")
    for n in nodes:
        name = n.get("name","")
        ntype = n.get("type","")
        params = n.get("parameters",{})
        if ntype != "n8n-nodes-base.code": continue
        if "JavaScript3" in name:
            params["jsCode"] = DEDUP_CODE
            n["parameters"] = params
            fixes.append("FORCED DEDUP: " + name)
            changed = True
        elif "JavaScript4" in name:
            params["jsCode"] = WRITE_DEDUP_CODE
            n["parameters"] = params
            fixes.append("FORCED WRITE: " + name)
            changed = True

if changed:
    cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
               (json.dumps(nodes, ensure_ascii=False), wf_id))
    print("Saved: " + str(fixes))

conn.commit()
conn.close()

# Рестарт
subprocess.run(["docker","start","n8n"], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen("http://localhost:5678/healthz", timeout=5)
        print("n8n UP!")
        break
    except: pass

os.makedirs("/data", exist_ok=True)
with open("/data/published_titles.json","w") as f: json.dump([], f)
time.sleep(2)

# Логин и запуск
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
exec_id = None
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    run_req = urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/run",
        data=json.dumps({"runData":{},"startNodes":[],"destinationNode":""}).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    with opener.open(run_req, timeout=30) as r:
        run_resp = json.loads(r.read())
    exec_id = run_resp.get("data",{}).get("executionId") or run_resp.get("executionId")
    print("RSS started: exec_id=" + str(exec_id))
except Exception as e:
    print("Run error: " + str(e)[:100])

tg(
    "<b>RSS FIX + RUN</b>\n\n"
    "<b>Исправлено:</b>\n" + ("\n".join("• " + f for f in fixes) if fixes else "нет") +
    "\n\n<b>Запущен:</b> exec_id=" + str(exec_id) +
    "\nЖди ~90 сек — результат в @grandvest_realty!"
)
print("DONE. fixes=" + str(fixes))
