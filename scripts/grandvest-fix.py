import sqlite3, json, subprocess, urllib.request, urllib.parse
from datetime import datetime

DB = "/opt/n8n/n8n_data/database.sqlite"
BOT = "8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CID = "5340000158"
CODE = 'const postText=$("8. \u041f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430 \u0434\u0430\u043d\u043d\u044b\u0445 \u043f\u043e\u0441\u0442\u0430").first().json.tg_post;\nconst imageUrl=$("HTTP Request \u2014 fal.ai").first().json.images[0].url;\nconst botToken="8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw";\nconst chatId="-1003971323034";\nconst resp=await fetch("https://api.telegram.org/bot"+botToken+"/sendPhoto",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chat_id:chatId,photo:imageUrl,caption:postText,parse_mode:"HTML"})});\nconst result=await resp.json();\nreturn [{json:result}];'
SCH = {"rule": {"interval": [{"field": "cronExpression", "expression": "0 0 8-20 * * *"}]}}

def tg(m):
    try:
        url = "https://api.telegram.org/bot" + BOT + "/sendMessage"
        data = urllib.parse.urlencode({"chat_id": CID, "text": m, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        urllib.request.urlopen(req, timeout=10)
        print("TG sent OK")
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
            fixes.append("Активирован: " + wname)
        for n in nodes:
            nm = n.get("name", "")
            nt = n.get("type", "")
            if "RSS" in wname and "scheduleTrigger" in nt:
                cur_s = json.dumps(n.get("parameters", {}))
                if "*/5" in cur_s or "*/30" in cur_s or "cronExpression" not in cur_s:
                    n["parameters"] = SCH
                    changed = True
                    fixes.append("Расписание исправлено: " + wname)
            if "\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430" in nm:
                c = n.get("parameters", {}).get("jsCode", "")
                if "python3" in c or "import sqlite" in c or "$credentials" in c or len(c.strip()) < 10:
                    n["parameters"]["jsCode"] = CODE
                    changed = True
                    fixes.append("Исправлен узел: " + wname)
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
    ui = "Dostupен"
except:
    ui = "Nedostupen"

now = datetime.now().strftime("%d.%m.%Y %H:%M")
if fixes:
    msg = "Grandvest Agent - Ispravleniya\n\n" + "\n".join(fixes) + "\n\nn8n: " + ui + "\n" + now + " MSK"
else:
    msg = "Grandvest Agent - OK\n\n" + "\n".join(status) + "\n\nn8n: " + ui + "\n" + now + " MSK"

tg(msg)
print("Done:", fixes if fixes else "OK")
