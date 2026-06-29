import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time, http.cookiejar

DB = "/opt/n8n/n8n_data/database.sqlite"
BOT = os.environ.get("TG_BOT","")
CHAT = "5340000158"
RSS_WF_ID = "SIPnV2mqmgMqUkLb"

def tg(msg):
    if not BOT: print("TG:", msg[:300]); return
    d = urllib.parse.urlencode({"chat_id":CHAT,"text":msg[:4096],"parse_mode":"HTML"}).encode()
    try: urllib.request.urlopen(urllib.request.Request("https://api.telegram.org/bot"+BOT+"/sendMessage",data=d,method="POST"),timeout=15)
    except Exception as e: print("TG err:", e)

print("=== RSS SOURCE DIAGNOSTIC ===")

# 1. Читаем все RSS URL из workflow
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id=?", (RSS_WF_ID,))
row = cur.fetchone()
wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)

rss_urls = []
for n in nodes:
    ntype = n.get("type","")
    params = n.get("parameters",{})
    name = n.get("name","")
    if ntype == "n8n-nodes-base.httpRequest":
        url = params.get("url","")
        method = params.get("method","GET")
        if method == "GET" and ("google.com/rss" in url or "ria.ru" in url or "cian.ru" in url or "vedomosti" in url):
            rss_urls.append((name, url))

print(f"Found {len(rss_urls)} RSS sources")

# 2. Тестируем каждый URL
results = []
for name, url in rss_urls:
    try:
        # Подставляем реальный URL если есть выражения n8n
        real_url = url
        if "={{" in url:
            real_url = url.split("={{")[0].strip()
        req = urllib.request.Request(real_url, headers={"User-Agent":"Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        content = resp.read()
        size = len(content)
        # Считаем количество items в RSS
        import re
        items_count = len(re.findall(b"<item>|<entry>", content))
        status = "OK " + str(items_count) + " items"
        print(f"  {name}: {status} ({size} bytes)")
        results.append(name + ": " + status)
    except Exception as e:
        err = str(e)[:60]
        print(f"  {name}: FAIL - {err}")
        results.append(name + ": FAIL - " + err)

# 3. Читаем текущий StaticData дедупликации из SQLite
cur.execute("SELECT key, value FROM workflow_static_data WHERE workflowId=? AND type='global'", (RSS_WF_ID,))
static_rows = cur.fetchall()
dedup_count = 0
if static_rows:
    for key, val in static_rows:
        try:
            sd = json.loads(val)
            titles = sd.get("publishedTitles", [])
            dedup_count = len(titles)
            print(f"StaticData publishedTitles: {dedup_count} items")
            if titles:
                print("  Last 3:", titles[-3:])
        except: pass

# 4. Сброс StaticData если > 0
if dedup_count > 0:
    print("Resetting StaticData...")
    new_sd = json.dumps({"publishedTitles": []})
    cur.execute("UPDATE workflow_static_data SET value=? WHERE workflowId=? AND type='global'",
               (new_sd, RSS_WF_ID))
    conn.commit()
    print("StaticData reset!")
    
conn.close()

# 5. Перезапускаем n8n и запускаем RSS
subprocess.run(["docker","restart","n8n"], capture_output=True, timeout=40)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen("http://localhost:5678/healthz", timeout=5)
        print("n8n UP!")
        break
    except: pass

time.sleep(3)

# 6. Запускаем RSS workflow
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
        resp = json.loads(r.read())
    exec_id = resp.get("data",{}).get("executionId") or resp.get("executionId","?")
    print("RSS started: " + str(exec_id))
except Exception as e:
    print("Run error: " + str(e)[:100])

results_str = "\n".join(results)
tg(
    "<b>RSS DIAGNOSTIC</b>\n\n"
    "<b>Источники:</b>\n" + results_str +
    "\n\n<b>StaticData dedup:</b> " + str(dedup_count) + " titles (сброшено)" +
    "\n\n<b>RSS запущен:</b> exec_id=" + str(exec_id) +
    "\nЖди 90 сек — результат в @grandvest_realty!"
)
print("DONE")
