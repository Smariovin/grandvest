import sqlite3, json, subprocess, urllib.request, urllib.parse
from datetime import datetime
DB="/opt/n8n/n8n_data/database.sqlite"
BOT="8672691136:AAF4yJeigfcmn6eCCkKC8GdJvxDb0o9cNnDg"
CID="5340000158"
CODE=('const postText=$("8. Подготовка данных поста").first().json.tg_post;\nconst imageUrl=$("HTTP Request — fal.ai").first().json.images[0].url;\nconst botToken="8672691136:AAF4yJeigfcmn6eCCkKC8GdJvxDb0o9cNnDg";\nconst chatId="-1003971323034";\nconst resp=await fetch("https://api.telegram.org/bot"+botToken+"/sendPhoto",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chat_id:chatId,photo:imageUrl,caption:postText,parse_mode:"HTML"})});\nconst result=await resp.json();\nreturn [{json:result}];')
SCH={"rule":{"interval":[{"field":"cronExpression","expression":"0 0 8-20 * * *"}]}}
def tg(m):
    try:
        d=urllib.parse.urlencode({"chat_id":CID,"text":m,"parse_mode":"HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request("https://api.telegram.org/bot"+BOT+"/sendMessage",d),timeout=10)
    except: pass
fixes=[];status=[]
try:
    con=sqlite3.connect(DB);cur=con.cursor()
    cur.execute("SELECT id,name,active,nodes FROM workflow_entity")
    for wid,wname,active,nj in cur.fetchall():
        nodes=json.loads(nj);changed=False
        if not active:
            cur.execute("UPDATE workflow_entity SET active=1 WHERE id=?",(wid,))
            fixes.append("⚡ Активирован: "+wname)
        for n in nodes:
            nm=n.get("name","");nt=n.get("type","")
            if "RSS" in wname and "scheduleTrigger" in nt:
                cur_s=json.dumps(n.get("parameters",{}))
                if "*/5" in cur_s or "*/30" in cur_s or "cronExpression" not in cur_s:
                    n["parameters"]=SCH;changed=True
                    fixes.append("⏰ Расписание исправлено: "+wname)
            if "Отправка" in nm:
                c=n.get("parameters",{}).get("jsCode","")
                if "python3" in c or "import sqlite" in c or "$credentials" in c or len(c.strip())<10:
                    n["parameters"]["jsCode"]=CODE;changed=True
                    fixes.append("🔧 Исправлен узел Отправка: "+wname)
        if changed:
            cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",(json.dumps(nodes,ensure_ascii=False),wid))
        status.append(("✅" if active else "❌")+" "+wname)
    con.commit();con.close()
    if fixes: subprocess.run(["docker","restart","n8n"],capture_output=True)
except Exception as e:
    fixes.append("❌ Ошибка: "+str(e)[:100])
try: urllib.request.urlopen("http://localhost:5678/healthz",timeout=5);ui="✅ Доступен"
except: ui="❌ Недоступен"
now=datetime.now().strftime("%d.%m.%Y %H:%M")
msg=("🤖 <b>Grandvest Agent — Исправления</b>\n\n"+"\n".join(fixes) if fixes else "🤖 <b>Grandvest Agent — OK</b>\n\n"+"\n".join(status))+"\n\n🌐 n8n: "+ui+"\n🕐 "+now+" МСК"
tg(msg);print("Done:",fixes if fixes else "OK")
