#!/usr/bin/env python3
"""Fix ALL Code nodes with require(fs) in RSS workflow"""
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

# Правильный код дедупликации без require(fs)
DEDUP_CODE = """const items = $input.all();
const staticData = $getWorkflowStaticData("global");
if (!staticData.publishedTitles) staticData.publishedTitles = [];
const published = staticData.publishedTitles;
const unique = [];
for (const item of items) {
  const title = (item.json.title || item.json.text || "").trim().toLowerCase().substring(0, 80);
  if (!title) continue;
  const isDup = published.some(function(p) { return p.substring(0,80) === title; });
  if (!isDup) unique.push(item);
  else console.log("Dup skipped:", title.substring(0,40));
}
if (staticData.publishedTitles.length > 500) {
  staticData.publishedTitles = staticData.publishedTitles.slice(-300);
}
console.log("Dedup: in=" + items.length + " out=" + unique.length);
return unique.slice(0, 1);"""

# Код записи в дедупликацию без require(fs)
WRITE_DEDUP_CODE = """const item = $input.first().json;
const title = (item.title || item.text || item.tg_post || "").trim().toLowerCase().substring(0, 80);
if (title) {
  const staticData = $getWorkflowStaticData("global");
  if (!staticData.publishedTitles) staticData.publishedTitles = [];
  if (!staticData.publishedTitles.includes(title)) {
    staticData.publishedTitles.push(title);
  }
}
return [$input.first()];"""

print("=== FIX ALL FS NODES ===")

subprocess.run(["docker","stop","n8n"], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id=?", (RSS_WF_ID,))
row = cur.fetchone()

if not row:
    tg("ERROR: RSS workflow not found!")
    conn.close()
    exit(1)

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
fixes = []
changed = False

print("RSS: " + wf_name + " | nodes: " + str(len(nodes)))

for n in nodes:
    name = n.get("name","")
    ntype = n.get("type","")
    params = n.get("parameters",{})

    if ntype != "n8n-nodes-base.code":
        continue

    code = params.get("jsCode","")
    print("Code node [" + name + "]: " + code[:80])

    # Любой Code узел с require("fs") или require('fs')
    if "require(" in code and "fs" in code:
        print("  -> HAS require(fs)! Fixing...")

        # Определяем тип узла по содержимому
        if "readFileSync" in code and "writeFileSync" not in code:
            # Только чтение — это дедупликация
            params["jsCode"] = DEDUP_CODE
            fixes.append("DEDUP: " + name)
        elif "writeFileSync" in code or "push" in code:
            # Запись — это write dedup
            params["jsCode"] = WRITE_DEDUP_CODE
            fixes.append("WRITE_DEDUP: " + name)
        else:
            # По умолчанию — dedup
            params["jsCode"] = DEDUP_CODE
            fixes.append("DEDUP_DEFAULT: " + name)

        n["parameters"] = params
        changed = True
        print("  FIXED!")

if changed:
    cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
               (json.dumps(nodes, ensure_ascii=False), wf_id))
    print("Saved " + str(len(fixes)) + " fixes")
else:
    print("No require(fs) found - checking manually...")
    # Принудительно исправляем по именам
    for n in nodes:
        name = n.get("name","")
        ntype = n.get("type","")
        params = n.get("parameters",{})
        if ntype != "n8n-nodes-base.code": continue
        if "JavaScript3" in name or "JavaScript4" in name:
            code = params.get("jsCode","")
            print("  Force fixing " + name + ": " + code[:60])
            if "JavaScript4" in name:
                params["jsCode"] = WRITE_DEDUP_CODE
            else:
                params["jsCode"] = DEDUP_CODE
            n["parameters"] = params
            fixes.append("FORCED: " + name)
            changed = True
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

# Рестарт n8n
subprocess.run(["docker","start","n8n"], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen("http://localhost:5678/healthz", timeout=5)
        print("n8n UP!")
        break
    except: pass

# Сброс дедупликации
os.makedirs("/data", exist_ok=True)
with open("/data/published_titles.json","w") as f: json.dump([], f)

# Сбрасываем StaticData RSS workflow через API
time.sleep(3)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    # Сброс staticData
    opener.open(urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/activate",
        data=b"{}", headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    print("Activated")
    # Запускаем
    run_req = urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/run",
        data=json.dumps({"runData":{},"startNodes":[],"destinationNode":""}).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    with opener.open(run_req, timeout=30) as r:
        run_resp = json.loads(r.read())
    exec_id = run_resp.get("data",{}).get("executionId") or run_resp.get("executionId")
    print("Run started: exec_id=" + str(exec_id))
    tg(
        "<b>RSS FIX + RUN</b>\n\n"
        "<b>Исправлено:</b>\n" + ("\n".join("• " + f for f in fixes) if fixes else "• нет") +
        "\n\n<b>Запущен:</b> exec_id=" + str(exec_id) +
        "\nЖди ~90 сек — результат в @grandvest_realty!"
    )
except Exception as e:
    print("API error: " + str(e))
    tg("<b>RSS FIX DONE</b>\n\nИсправлено:\n" + ("\n".join(fixes) if fixes else "нет") +
       "\n\nn8n перезапущен. Запусти вручную: Execute workflow")

print("DONE. fixes=" + str(fixes))