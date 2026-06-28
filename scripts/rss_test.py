#!/usr/bin/env python3
"""RSS Test - запускаем Execute workflow и мониторим"""
import json, urllib.request, urllib.parse, os, time, http.cookiejar, subprocess

BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
RSS_WF_ID = 'SIPnV2mqmgMqUkLb'

def tg(msg):
    if not BOT: print("TG:", msg[:200]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== RSS TEST ===")

# 1. Сброс дедупликации
import os as os2
os2.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)
print("Dedup reset")

# 2. n8n логин
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    print("n8n login OK")
except Exception as e:
    print("Login error: " + str(e))
    tg("ERROR: n8n login failed: " + str(e))
    exit(1)

# 3. Активируем RSS workflow (на всякий случай)
try:
    opener.open(urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/activate",
        data=b'{}', headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    print("RSS workflow activated")
except Exception as e:
    print("Activation: " + str(e))

# 4. Запускаем Execute через n8n API
print("Starting RSS workflow execution...")
try:
    exec_req = urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/run",
        data=b'{}',
        headers={"Content-Type":"application/json"},
        method="POST"
    )
    with opener.open(exec_req, timeout=15) as resp:
        run_data = json.loads(resp.read())
    exec_id = run_data.get('data',{}).get('executionId') or run_data.get('executionId','?')
    print("Execution started: " + str(exec_id))
    tg("RSS workflow запущен! ExecutionId=" + str(exec_id) + "\nЖди пост в @grandvest_realty (~60 сек)")
except Exception as e:
    print("Execute error: " + str(e))
    # Пробуем через trigger endpoint
    try:
        trigger_req = urllib.request.Request(
            "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/trigger",
            data=b'{}',
            headers={"Content-Type":"application/json"},
            method="POST"
        )
        with opener.open(trigger_req, timeout=15) as resp:
            trigger_data = json.loads(resp.read())
        print("Trigger: " + str(trigger_data)[:200])
    except Exception as e2:
        print("Trigger also failed: " + str(e2))

# 5. Мониторим последние executions
print("Waiting 90s for RSS to complete...")
time.sleep(90)

try:
    with opener.open("http://localhost:5678/rest/executions?limit=3&workflowId=" + RSS_WF_ID, timeout=10) as r:
        ed = json.loads(r.read())
    
    execs = ed.get('data',{}).get('data', ed.get('data',[]))
    
    all_info = []
    for ex in (execs[:2] if isinstance(execs,list) else []):
        status = ex.get('status','?')
        started = str(ex.get('startedAt','?'))[:16]
        ex_info = status + " @ " + started
        
        rd = ex.get('data',{}).get('resultData',{}).get('runData',{})
        lines = []
        for nn, nd in list(rd.items()):
            if nd and nd[0]:
                items_d = nd[0].get('data',{}).get('main',[[]])[0]
                has = bool(items_d and items_d[0])
                txt = ""
                if has:
                    s = items_d[0].get('json',{})
                    for f in ['title','tg_post','generated_content','score','images']:
                        if f in s:
                            v = s[f]
                            txt = (str(v)[:50] if not isinstance(v,list) else str(len(v))+" items") if v else ""
                            break
                lines.append(("OK " if has else "NO ") + nn[:28] + ": " + txt)
        ex_info += "\n" + "\n".join(lines[:15])
        
        err = ex.get('data',{}).get('resultData',{}).get('error')
        if err:
            ex_info += "\nERR: " + str(err)[:150]
        
        all_info.append(ex_info)
    
    exec_report = "\n\n".join(all_info) if all_info else "no executions found"
    
    tg(
        "<b>RSS TEST RESULT</b>\n\n"
        "<b>Executions:</b>\n" + exec_report[:2000]
    )
except Exception as e:
    tg("RSS test done, check @grandvest_realty for new post. API err: " + str(e)[:100])

print("DONE")
