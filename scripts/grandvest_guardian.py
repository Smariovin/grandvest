#!/usr/bin/env python3
"""Minimal RSS restore - only URL fix + dedup reset + run"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, http.cookiejar

DB = "/opt/n8n/n8n_data/database.sqlite"
BOT = os.environ.get("TG_BOT","")
CHAT = "5340000158"
RSS_WF_ID = "SIPnV2mqmgMqUkLb"

def tg(msg):
    if not BOT: print(msg); return
    d = urllib.parse.urlencode({"chat_id":CHAT,"text":msg[:4096],"parse_mode":"HTML"}).encode()
    try: urllib.request.urlopen(urllib.request.Request("https://api.telegram.org/bot"+BOT+"/sendMessage",data=d,method="POST"),timeout=15)
    except Exception as e: print("TG:",e)

URLS = {
    "HTTP Request":  "https://news.google.com/rss/search?q=%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request1": "https://news.google.com/rss/search?q=%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%BE%D1%84%D0%B8%D1%81%D0%BE%D0%B2+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request2": "https://news.google.com/rss/search?q=%D1%81%D0%BA%D0%BB%D0%B0%D0%B4%D1%8B+%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request3": "https://news.google.com/rss/search?q=%D1%82%D0%BE%D1%80%D0%B3%D0%BE%D0%B2%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request4": "https://news.google.com/rss/search?q=%D0%B4%D0%B5%D0%B2%D0%B5%D0%BB%D0%BE%D0%BF%D0%BC%D0%B5%D0%BD%D1%82+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request5": "https://news.google.com/rss/search?q=%D0%B8%D0%BD%D0%B2%D0%B5%D1%81%D1%82%D0%B8%D1%86%D0%B8%D0%B8+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request10": "https://www.vedomosti.ru/rss/rubric/realty",
    "РИА Недвижимость": "https://realty.ria.ru/export/rss2/index.xml",
    "Циан": "https://www.cian.ru/rss/",
}

print("=== MINIMAL RSS RESTORE ===")
subprocess.run(["docker","stop","n8n"], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id=?", (RSS_WF_ID,))
row = cur.fetchone()
if not row: print("NOT FOUND"); exit(1)

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
fixes = []

for n in nodes:
    name = n.get("name","")
    ntype = n.get("type","")
    params = n.get("parameters",{})
    if ntype == "n8n-nodes-base.httpRequest" and name in URLS:
        old = params.get("url","")[:40]
        params["url"] = URLS[name]
        params["method"] = "GET"
        params.pop("bodyContentType", None)
        params.pop("jsonBody", None)
        params.pop("specifyBody", None)
        n["parameters"] = params
        fixes.append(name + ": " + old + " -> OK")
        print("Fixed: " + name)

try:
    cur.execute("UPDATE workflow_static_data SET value=? WHERE workflowId=? AND type=?",
               (json.dumps({"publishedTitles":[]}), RSS_WF_ID, "global"))
    fixes.append("StaticData reset")
except Exception as e:
    print("StaticData:", str(e))

cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
           (json.dumps(nodes, ensure_ascii=False), wf_id))
conn.commit()
conn.close()
print("Fixes: " + str(fixes))

subprocess.run(["docker","start","n8n"], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try: urllib.request.urlopen("http://localhost:5678/healthz",timeout=5); print("UP!"); break
    except: pass

time.sleep(3)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
exec_id = None
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    rr = urllib.request.Request(
        "http://localhost:5678/rest/workflows/"+RSS_WF_ID+"/run",
        data=json.dumps({"runData":{},"startNodes":[],"destinationNode":""}).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    with opener.open(rr, timeout=30) as r: resp = json.loads(r.read())
    exec_id = resp.get("data",{}).get("executionId") or resp.get("executionId","?")
    print("Started: " + str(exec_id))
except Exception as e: print("Run err: " + str(e)[:80])

lines = ["<b>RSS MINIMAL RESTORE</b>",""]
lines += ["• " + f for f in fixes]
lines += ["","exec_id=" + str(exec_id),"Жди 90 сек — пост в @grandvest_realty!"]
tg("\n".join(lines))
print("DONE")
