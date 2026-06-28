#!/usr/bin/env python3
"""Read last RSS execution and show per-node output"""
import json, urllib.request, urllib.parse, os, time, http.cookiejar

BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
RSS_WF_ID = 'SIPnV2mqmgMqUkLb'

def tg(msg):
    if not BOT: print("TG:", msg[:300]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== RSS EXEC CHECK ===")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
opener.open(urllib.request.Request("http://localhost:5678/rest/login",
    data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)

# Получаем последний execution с полными данными
with opener.open("http://localhost:5678/rest/executions?limit=1&workflowId=" + RSS_WF_ID + "&includeData=true", timeout=15) as r:
    ed = json.loads(r.read())

execs = ed.get('data',{}).get('data', ed.get('data',[]))
if not execs:
    tg("No RSS executions found!")
    exit(0)

ex = execs[0]
status = ex.get('status','?')
started = str(ex.get('startedAt','?'))[:16]
print("Execution: " + status + " @ " + started)

rd = ex.get('data',{}).get('resultData',{}).get('runData',{})
lines = ["Status: " + status + " @ " + started, ""]

# Показываем каждый узел с деталями
for nn, nd in list(rd.items()):
    if nd and nd[0]:
        node_run = nd[0]
        items_d = node_run.get('data',{}).get('main',[[]])[0]
        has = bool(items_d and items_d[0])
        
        txt = ""
        keys = []
        if has:
            s = items_d[0].get('json',{})
            keys = list(s.keys())[:6]
            for f in ['title','text','tg_post','generated_content','score','topic','images','url']:
                if f in s:
                    v = s[f]
                    if isinstance(v, list):
                        txt = str(len(v)) + " items"
                    elif isinstance(v, dict):
                        txt = str(v)[:40]
                    else:
                        txt = str(v)[:60]
                    break
        
        err_info = ""
        err = node_run.get('error')
        if err:
            err_info = " ERR:" + str(err)[:50]
        
        icon = "OK " if has else "NO "
        lines.append(icon + nn[:30] + ": " + txt + err_info)
        print(icon + nn + ": keys=" + str(keys) + " txt=" + txt + err_info)

# Общая ошибка
top_err = ex.get('data',{}).get('resultData',{}).get('error')
if top_err:
    lines.append("\nTOP ERROR: " + str(top_err)[:200])
    print("TOP ERROR: " + str(top_err)[:200])

tg("<b>RSS EXECUTION DETAILS</b>\n\n" + "\n".join(lines[:30]))
print("DONE")
