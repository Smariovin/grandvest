#!/usr/bin/env python3
import json, urllib.request, urllib.parse, os, time, http.cookiejar, sqlite3

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

print("=== RSS RUN ===")
os.makedirs("/data", exist_ok=True)
with open("/data/published_titles.json","w") as f: json.dump([], f)
print("Dedup reset")

# Логин
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
opener.open(urllib.request.Request("http://localhost:5678/rest/login",
    data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
print("Login OK")

# Метод 1: /rest/workflows/{id}/run
run_ok = False
exec_id = None
print("Trying /run endpoint...")
try:
    payload = json.dumps({"runData":{},"startNodes":[],"destinationNode":""}).encode()
    req = urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/run",
        data=payload, headers={"Content-Type":"application/json"}, method="POST")
    with opener.open(req, timeout=30) as r:
        resp = json.loads(r.read())
    exec_id = resp.get("data",{}).get("executionId") or resp.get("executionId")
    print("Run OK: exec_id=" + str(exec_id))
    run_ok = True
except Exception as e:
    print("Run failed: " + str(e)[:150])

if not run_ok:
    tg("RSS API run failed. Запусти вручную:\n\n1. Открой http://85.239.61.157:5678\n2. Workflow 1. Сбор новостей RSS\n3. Кнопка Execute workflow\n\nПотом Executions → скриншот")
    exit(0)

tg("RSS запущен! exec_id=" + str(exec_id) + "\nЖди 90 сек — результат придёт автоматически")
print("Waiting 100s...")
time.sleep(100)

# Читаем результат из SQLite
conn = sqlite3.connect(DB)
cur = conn.cursor()
sql = "SELECT ee.id, ee.status, ee.startedAt, ed.data FROM execution_entity ee LEFT JOIN execution_data ed ON ee.id = ed.executionId WHERE ee.workflowId = ? ORDER BY ee.id DESC LIMIT 2"
cur.execute(sql, (RSS_WF_ID,))
rows = cur.fetchall()
conn.close()

if not rows:
    tg("exec_id=" + str(exec_id) + " — execution_entity пуста. Статус неизвестен.")
    exit(0)

report = ["exec_id=" + str(exec_id), ""]
for row in rows:
    ex_id, status, started, data_raw = row
    report.append(str(ex_id) + " | " + str(status) + " | " + str(started)[:16])
    if data_raw:
        try:
            ed = json.loads(data_raw)
            rd = ed.get("resultData",{}).get("runData",{})
            for nn, nd in list(rd.items()):
                if nd and nd[0]:
                    items_d = nd[0].get("data",{}).get("main",[[]])[0]
                    has = bool(items_d and items_d[0])
                    txt = ""
                    if has:
                        s = items_d[0].get("json",{})
                        for f in ["title","score","tg_post","generated_content","images"]:
                            if f in s:
                                v = s[f]
                                txt = str(v)[:50] if not isinstance(v,(list,dict)) else type(v).__name__
                                break
                    err = nd[0].get("error")
                    err_s = (" ERR:" + str(err)[:40]) if err else ""
                    report.append(("OK " if has else "NO ") + nn[:28] + ": " + txt + err_s)
            top_err = ed.get("resultData",{}).get("error")
            if top_err:
                report.append("TOPERR: " + str(top_err)[:100])
        except Exception as e:
            report.append("parse err: " + str(e)[:50])

tg("<b>RSS EXECUTION RESULT</b>\n\n" + "\n".join(report[:25]))
print("DONE")