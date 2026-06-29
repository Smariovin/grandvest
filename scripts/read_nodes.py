import sqlite3, json, urllib.request, urllib.parse, http.cookiejar, os, time

N8N = "http://localhost:5678"
TG_WF = "F24jvKiXJIs4wRiZ"
try: BOT = open("/tmp/.tb").read().strip()
except: BOT = ""
CHAT = "5340000158"

def tg(msg):
    if not BOT: print(msg[:300]); return
    d = urllib.parse.urlencode({"chat_id":CHAT,"text":msg[:4096],"parse_mode":"HTML"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(
        "https://api.telegram.org/bot"+BOT+"/sendMessage",data=d,method="POST"),timeout=15)
    except Exception as e: print("TG:",e)

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
opener.open(urllib.request.Request(N8N+"/rest/login",
    data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)

with opener.open(N8N+"/rest/executions?limit=1&workflowId="+TG_WF, timeout=15) as r:
    ed = json.loads(r.read())
execs = ed.get("data",{}).get("data", ed.get("data",[]))

if not execs:
    tg("Нет executions!")
else:
    ex = execs[0]
    status = ex.get("status","?")
    started = str(ex.get("startedAt","?"))[:16]
    rd = ex.get("data",{}).get("resultData",{}).get("runData",{})
    
    order = ["Webhook","2. Дедупликация входящих","1. Парсинг HTML Telegram",
             "Claude — оценка поста","Code — фильтр оценки",
             "6. Извлечение текста поста","HTTP Request — генерация поста",
             "8. Подготовка данных поста","HTTP Request — fal.ai",
             "9. Отправка в Telegram","10. Запись в дедупликацию"]
    
    lines = ["<b>21:56 МСК TRACE</b>", status+" @ "+started, ""]
    for nn in order:
        nd = rd.get(nn)
        if nd is None:
            lines.append("⬜ "+nn[:28])
            continue
        if nd and nd[0]:
            items = nd[0].get("data",{}).get("main",[[]])[0]
            has = bool(items and items[0])
            err = nd[0].get("error")
            if err:
                lines.append("❌ "+nn[:28]+": "+str(err)[:50])
            elif has:
                s2 = items[0].get("json",{})
                # Показываем ключевые значения
                info = {}
                for f in ["text","score","tg_post","image_url","dispatch_ok","choices"]:
                    if f in s2:
                        v = s2[f]
                        info[f] = str(v)[:40] if not isinstance(v,(list,dict)) else f"[{type(v).__name__}]"
                lines.append("✅ "+nn[:28]+": "+str(info))
            else:
                lines.append("🛑 "+nn[:28]+": NO OUTPUT — стоп")
    
    top_err = ex.get("data",{}).get("resultData",{}).get("error")
    if top_err:
        lines.append("TOP ERR: "+str(top_err)[:80])
    
    tg("\n".join(lines))

print("DONE")
