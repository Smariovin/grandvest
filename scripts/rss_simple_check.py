#!/usr/bin/env python3
import json, urllib.request, urllib.parse, os, http.cookiejar

BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
RSS_WF_ID = 'SIPnV2mqmgMqUkLb'

def tg(msg):
    if not BOT: print("TG:", msg[:300]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
opener.open(urllib.request.Request("http://localhost:5678/rest/login",
    data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
print("Login OK")

# Получаем список последних executions без данных
with opener.open("http://localhost:5678/rest/executions?limit=5&workflowId=" + RSS_WF_ID, timeout=15) as r:
    ed = json.loads(r.read())

execs = ed.get('data',{}).get('data', ed.get('data',[]))
print("Executions found: " + str(len(execs)))

lines = []
for ex in (execs[:3] if isinstance(execs,list) else []):
    status = ex.get('status','?')
    started = str(ex.get('startedAt','?'))[:16]
    stopped = str(ex.get('stoppedAt','?'))[:16]
    mode = ex.get('mode','?')
    lines.append(status + " | " + started + " -> " + stopped + " | " + mode)
    print(status + " | " + started)

# Берём ID последнего и читаем его детально
if execs:
    ex_id = execs[0].get('id')
    print("Reading exec " + str(ex_id) + " in detail...")
    try:
        with opener.open("http://localhost:5678/rest/executions/" + str(ex_id), timeout=30) as r2:
            ex_detail = json.loads(r2.read())
        
        ex_data = ex_detail.get('data',{})
        rd = ex_data.get('resultData',{}).get('runData',{})
        
        node_lines = []
        for nn, nd in list(rd.items()):
            if nd and nd[0]:
                items_d = nd[0].get('data',{}).get('main',[[]])[0]
                has = bool(items_d and items_d[0])
                txt = ""
                if has:
                    s = items_d[0].get('json',{})
                    for f in ['title','text','score','tg_post','generated_content','images']:
                        if f in s:
                            v = s[f]
                            txt = (str(v)[:50] if not isinstance(v,(list,dict)) else str(type(v).__name__)) if v else ""
                            break
                err = nd[0].get('error')
                err_str = (" ERR:" + str(err)[:40]) if err else ""
                node_lines.append(("OK " if has else "NO ") + nn[:28] + ": " + txt + err_str)
        
        top_err = ex_data.get('resultData',{}).get('error')
        if top_err:
            node_lines.append("TOPERR: " + str(top_err)[:100])
        
        tg(
            "<b>RSS EXEC DETAILS</b>\n\n"
            "<b>Последние runs:</b>\n" + "\n".join(lines) +
            "\n\n<b>Узлы execution #" + str(ex_id) + ":</b>\n" +
            "\n".join(node_lines[:20])
        )
    except Exception as e:
        tg("<b>RSS executions:</b>\n" + "\n".join(lines) + "\n\nDetail error: " + str(e)[:200])
else:
    tg("No RSS executions found at all!")

print("DONE")
