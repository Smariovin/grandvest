import sqlite3, json, subprocess, urllib.request, urllib.parse
from datetime import datetime

DB = "/opt/n8n/n8n_data/database.sqlite"
BOT = "8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CID = "5340000158"
SCH = {"rule": {"interval": [{"field": "cronExpression", "expression": "0 0 8-20 * * *"}]}}

def tg(m):
    try:
        url = "https://api.telegram.org/bot" + BOT + "/sendMessage"
        data = urllib.parse.urlencode({"chat_id": CID, "text": m, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("TG error:", e)

fixes = []
status = []

try:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT id,name,active,nodes FROM workflow_entity")
    for wid, wname, active, nj in cur.fetchall():
        nodes = json.loads(nj)
        changed = False
        if not active:
            cur.execute("UPDATE workflow_entity SET active=1 WHERE id=?", (wid,))
            fixes.append("Activated: " + wname)
        for n in nodes:
            nm = n.get("name", "")
            nt = n.get("type", "")
            if "RSS" in wname and "scheduleTrigger" in nt:
                cur_s = json.dumps(n.get("parameters", {}))
                if "*/5" in cur_s or "*/30" in cur_s or "cronExpression" not in cur_s:
                    n["parameters"] = SCH
                    changed = True
                    fixes.append("Schedule fixed: " + wname)
            # Node 9 (Otpravka) - DO NOT TOUCH, managed by grandvest-publisher.yml
        if changed:
            cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                        (json.dumps(nodes, ensure_ascii=False), wid))
        status.append(("OK" if active else "INACTIVE") + ": " + wname)
    con.commit()
    con.close()
    if fixes:
        subprocess.run(["docker", "restart", "n8n"], capture_output=True)
except Exception as e:
    fixes.append("ERROR: " + str(e)[:100])

try:
    urllib.request.urlopen("http://localhost:5678/healthz", timeout=5)
    ui = "OK"
except:
    ui = "DOWN"

now = datetime.now().strftime("%d.%m.%Y %H:%M")
patchi = "\n".join(fixes) if fixes else "none"
msg = (
    "Agent Grandvest\n\n"
    "n8n: " + ui + "\n"
    "Fixes: " + patchi + "\n"
    + now + " MSK"
)
tg(msg)
print("Done:", fixes if fixes else "OK")
