#!/usr/bin/env python3
"""Deep n8n diagnosis - reads execution data and sends to Telegram"""
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
PAT = os.environ.get('GH_PAT','')

def tg(msg):
    if not BOT: print(f"TG (no bot): {msg[:200]}"); return
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print(f'TG err: {e}')

print("=== DEEP DIAGNOSIS ===")

# 1. Read ALL nodes in workflow F24jvKiXJIs4wRiZ
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id,name,nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()

if not row:
    print("ERROR: workflow not found!")
    tg("ERROR: Workflow F24jvKiXJIs4wRiZ not found in DB!")
    exit(1)

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
print(f"Workflow: {wf_name} | {len(nodes)} nodes")

node_report = []
fixes = []
changed = False

for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    
    if ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode','')
        node_report.append(f"Code|{name}|{len(code)}ch")
        print(f"\nCode node: [{name}]")
        print(code[:600])
    
    elif ntype == 'n8n-nodes-base.httpRequest':
        url_v = params.get('url','')
        bct = params.get('bodyContentType','?')
        jb = params.get('jsonBody','')
        spec = params.get('specifyBody','?')
        node_report.append(f"HTTP|{name}|bct={bct}|spec={spec}|url={url_v[:30]}")
        print(f"\nHTTP node: [{name}]")
        print(f"  url={url_v[:60]}")
        print(f"  bct={bct!r} spec={spec!r}")
        print(f"  jsonBody={str(jb)[:300]}")
        
        # Fix openrouter nodes
        if 'openrouter' in url_v.lower() and bct != 'json':
            params['bodyContentType'] = 'json'
            params['specifyBody'] = 'json'
            n['parameters'] = params
            changed = True
            fixes.append(f"Fixed bct for {name}")

# Save fixes
if changed:
    cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
               (json.dumps(nodes,ensure_ascii=False), wf_id))
    print(f"\nSaved {len(fixes)} fixes")

conn.commit()
conn.close()

# 2. Read connections
conn2 = sqlite3.connect(DB)
cur2 = conn2.cursor()
cur2.execute("SELECT connections FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
conns_row = cur2.fetchone()
conn2.close()

if conns_row:
    conns = json.loads(conns_row[0]) if conns_row[0] else {}
    print(f"\nConnections ({len(conns)}):")
    for k,v in list(conns.items())[:10]:
        print(f"  {k} -> {str(v)[:100]}")

# 3. Restart if changed
if changed:
    subprocess.run(['docker','restart','n8n'], capture_output=True, timeout=40)
    time.sleep(20)

# 4. Check last execution SQLite
cur3 = sqlite3.connect(DB)
c3 = cur3.cursor()
c3.execute("SELECT id, status, startedAt, stoppedAt, data FROM execution_entity ORDER BY id DESC LIMIT 3")
execs = c3.fetchall()
cur3.close()

exec_report = []
for ex in execs:
    ex_id, st, started, stopped, ex_data = ex
    dur = "?"
    exec_report.append(f"#{ex_id} {st} {str(started)[:16]}")
    print(f"\nExec #{ex_id}: {st} @ {started}")
    
    if ex_data:
        try:
            ed = json.loads(ex_data)
            rd = ed.get('resultData',{}).get('runData',{})
            for nname, ndata in rd.items():
                if ndata and ndata[0]:
                    items = ndata[0].get('data',{}).get('main',[[]])[0]
                    if items and items[0]:
                        sample = items[0].get('json',{})
                        keys = list(sample.keys())[:5]
                        val_preview = str(list(sample.values())[:2])[:80]
                        print(f"  [{nname}] keys={keys} | {val_preview}")
                    else:
                        print(f"  [{nname}] NO OUTPUT")
            err = ed.get('error',{})
            if err:
                print(f"  ERROR: {str(err)[:200]}")
        except Exception as e:
            print(f"  parse error: {e}")

# 5. Test webhook
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)

print("\nTest webhook...")
try:
    payload = json.dumps({
        'channel': 'arendator_ru',
        'html': (
            '<div class="tgme_widget_message_text js-message_text">'
            'Аренда офисов в Москве 2026: по данным аналитиков JLL, ставки аренды '
            'в классе А выросли на 15% за первое полугодие. Средняя ставка в Москва-Сити '
            'составляет 55 000 рублей за кв.м в год. Спрос превышает предложение.'
            '</div>'
            '<time datetime="2026-06-28T22:00:00+00:00">22:00</time>'
        )
    }).encode('utf-8')
    res = urllib.request.urlopen(
        urllib.request.Request('http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type':'application/json'}), timeout=60)
    print(f"Webhook: {res.status}")
    webhook_ok = True
except Exception as e:
    print(f"Webhook error: {e}")
    webhook_ok = False

time.sleep(15)

# Read latest exec after test
conn4 = sqlite3.connect(DB)
c4 = conn4.cursor()
c4.execute("SELECT id, status, data FROM execution_entity ORDER BY id DESC LIMIT 1")
latest = c4.fetchone()
conn4.close()

latest_detail = "no data"
if latest:
    ex_id, st, ex_data = latest
    latest_detail = f"#{ex_id} {st}"
    if ex_data:
        try:
            ed = json.loads(ex_data)
            rd = ed.get('resultData',{}).get('runData',{})
            node_outputs = []
            for nname, ndata in rd.items():
                if ndata and ndata[0]:
                    items = ndata[0].get('data',{}).get('main',[[]])[0]
                    has_output = bool(items and items[0])
                    txt = ""
                    if has_output:
                        sample = items[0].get('json',{})
                        for fld in ['text','content','tg_post','postText','title']:
                            if fld in sample:
                                txt = str(sample[fld])[:60]
                                break
                    node_outputs.append(f"{'✅' if has_output else '❌'} {nname}: {txt}")
            latest_detail += "\n" + "\n".join(node_outputs)
            err = ed.get('error',{})
            if err:
                latest_detail += f"\nERROR: {str(err)[:200]}"
        except Exception as e:
            latest_detail += f" (parse err: {e})"

# 6. Send full report  
nodes_str = "\n".join(node_report)
tg(
    f"<b>DEEP DIAGNOSIS</b>\n\n"
    f"<b>Узлы ({len(node_report)}):</b>\n{nodes_str[:600]}\n\n"
    f"<b>Фиксы:</b>\n" + ("\n".join(fixes) if fixes else "нет") +
    f"\n\n<b>Webhook:</b> {'OK' if webhook_ok else 'FAIL'}\n\n"
    f"<b>Последний exec:</b>\n{latest_detail[:800]}"
)

print(f"\nDONE. fixes={fixes}, webhook={'OK' if webhook_ok else 'FAIL'}")
