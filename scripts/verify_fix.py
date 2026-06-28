#!/usr/bin/env python3
import json, urllib.request, urllib.parse, os, time, http.cookiejar

BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')

def tg(msg):
    if not BOT: print("TG:", msg[:200]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except: pass

print("=== VERIFY FIX ===")

# Сброс дедупликации
import os
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)

# Тест webhook
test_html = (
    '<div class="tgme_widget_message_text js-message_text">'
    'Торговая недвижимость Москвы 2026: по данным CBRE, трафик в ТЦ вырос на 12 процентов. '
    'Доля вакантных помещений снизилась до 6.5 процента. Арендные ставки на прайм-локации '
    'достигли 180 000 рублей за кв.м в год.'
    '</div>'
    '<time datetime="2026-06-28T23:00:00+00:00">23:00</time>'
)
payload = json.dumps({'channel':'CRERussia','html':test_html}).encode('utf-8')
try:
    res = urllib.request.urlopen(
        urllib.request.Request('http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type':'application/json'}), timeout=60)
    print("Webhook sent: " + str(res.status))
    webhook_ok = True
except Exception as e:
    print("Webhook error: " + str(e))
    webhook_ok = False

print("Waiting 25s for n8n to process...")
time.sleep(25)

# Читаем через n8n REST API
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()

try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    
    with opener.open("http://localhost:5678/rest/executions?limit=2&workflowId=F24jvKiXJIs4wRiZ",timeout=10) as r:
        ed = json.loads(r.read())
    
    execs = ed.get('data',{}).get('data', ed.get('data',[]))
    
    all_exec_info = []
    for ex in (execs[:2] if isinstance(execs,list) else []):
        status = ex.get('status','?')
        started = str(ex.get('startedAt','?'))[:16]
        ex_info = status + " @ " + started
        
        rd = ex.get('data',{}).get('resultData',{}).get('runData',{})
        node_lines = []
        for nn, nd in rd.items():
            if nd and nd[0]:
                items_d = nd[0].get('data',{}).get('main',[[]])[0]
                has = bool(items_d and items_d[0])
                txt = ""
                if has:
                    s = items_d[0].get('json',{})
                    for f in ['text','tg_post','content','score','images','url']:
                        if f in s:
                            v = s[f]
                            txt = (str(v)[:60] if not isinstance(v,list) else str(v[0])[:60]) if v else ""
                            break
                node_lines.append(("OK " if has else "NO ") + nn[:30] + ": " + txt)
        ex_info += "\n" + "\n".join(node_lines[:12])
        
        err = ex.get('data',{}).get('error') or ex.get('data',{}).get('resultData',{}).get('error')
        if err:
            ex_info += "\nERR: " + str(err)[:150]
        
        all_exec_info.append(ex_info)
    
    exec_report = "\n\n".join(all_exec_info) if all_exec_info else "no data"
    
except Exception as e:
    exec_report = "API error: " + str(e)

tg(
    "<b>VERIFY FIX RESULT</b>\n\n"
    "<b>Webhook:</b> " + ("OK" if webhook_ok else "FAIL") +
    "\n\n<b>n8n Executions:</b>\n" + exec_report[:1800]
)
print("DONE")
