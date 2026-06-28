#!/usr/bin/env python3
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
PAT = os.environ.get('GH_PAT','')

def tg(msg):
    if not BOT: print("NO BOT:", msg[:100]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== GRANDVEST DEEP DIAGNOSIS ===")
fixes = []
node_report = []

# 1. n8n health
try:
    urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
    print("n8n: UP")
except:
    print("n8n: DOWN - restarting")
    subprocess.run(['chown','1000:1000',DB], capture_output=True)
    subprocess.run(['chmod','644',DB], capture_output=True)
    subprocess.run(['docker','restart','n8n'], capture_output=True, timeout=40)
    time.sleep(20)
    fixes.append("n8n restarted")

# 2. Stop n8n and read SQLite
subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Read all workflows
cur.execute("SELECT id, name, active, nodes FROM workflow_entity")
all_wfs = cur.fetchall()
print(f"\nWorkflows in DB: {len(all_wfs)}")

changed_any = False
for wf_id, wf_name, active, nodes_raw in all_wfs:
    try: nodes = json.loads(nodes_raw)
    except: continue
    changed = False
    
    print(f"\n=== {wf_name} (active={active}) ===")
    
    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})
        
        if ntype == 'n8n-nodes-base.code':
            code = params.get('jsCode','')
            print(f"  Code[{name}]: {len(code)} chars")
            if code:
                print("    " + code[:300].replace("\n", "\n    "))
            node_report.append("Code|" + name + "|" + code[:80])
        
        elif ntype == 'n8n-nodes-base.httpRequest':
            url_v = params.get('url','')
            bct = params.get('bodyContentType','?')
            spec = params.get('specifyBody','?')
            jb = str(params.get('jsonBody',''))
            print(f"  HTTP[{name}]: bct={bct} spec={spec} url={url_v[:50]}")
            if jb: print(f"    body={jb[:200]}")
            node_report.append("HTTP|" + name + "|bct=" + bct + "|" + url_v[:40])
            
            # Fix openrouter nodes
            if 'openrouter' in url_v.lower() and bct != 'json':
                params['bodyContentType'] = 'json'
                params['specifyBody'] = 'json'
                n['parameters'] = params
                changed = True
                fix_msg = wf_name + ":" + name + " bct=json"
                fixes.append(fix_msg)
                print("    FIXED: bct=json")
            
            # Fix PAT in node 9 (Code nodes)
        
        elif ntype == 'n8n-nodes-base.if':
            conds = params.get('conditions',{})
            print(f"  IF[{name}]: {str(conds)[:100]}")
            node_report.append("IF|" + name)
    
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))
        changed_any = True
        print(f"  -> Saved changes for {wf_name}")

# Check Code nodes for PAT issues
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
tg_wf = cur.fetchone()
if tg_wf and PAT:
    wf_id, wf_name, nodes_raw = tg_wf
    nodes = json.loads(nodes_raw)
    changed = False
    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})
        code = params.get('jsCode','')
        if ntype == 'n8n-nodes-base.code' and ('github.com' in code or 'grandvest-publisher' in code):
            old_pats = re.findall('ghp_[A-Za-z0-9]{30,}', code)
            for op in old_pats:
                if op != PAT:
                    code = code.replace(op, PAT)
                    params['jsCode'] = code
                    n['parameters'] = params
                    changed = True
                    fixes.append("PAT updated in " + name)
    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))
        changed_any = True

conn.commit()
conn.close()

# 3. Start n8n
subprocess.run(['docker','start','n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except: pass

# 4. Reset dedup
os.makedirs('/data', exist_ok=True)
with open('/data/published_titles.json','w') as f: json.dump([], f)
print("Dedup reset")
time.sleep(2)

# 5. Test webhook
print("Test webhook...")
test_html = (
    '<div class="tgme_widget_message_text js-message_text">'
    'Рынок складской недвижимости Москвы 2026: по данным Knight Frank, ставки аренды '
    'в классе А выросли на 18 процентов. Средняя ставка составляет 8 500 рублей за кв.м в год. '
    'Вакантность снизилась до 1.2 процента — исторический минимум.'
    '</div>'
    '<time datetime="2026-06-28T22:30:00+00:00">22:30</time>'
)
payload = json.dumps({'channel':'arendator_ru','html':test_html}).encode('utf-8')
try:
    res = urllib.request.urlopen(
        urllib.request.Request('http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type':'application/json'}), timeout=60)
    print(f"Webhook: {res.status} {res.read().decode()[:100]}")
    webhook_ok = True
except Exception as e:
    print(f"Webhook error: {e}")
    webhook_ok = False

time.sleep(20)

# 6. Read last execution from SQLite
latest_detail = "no data"
try:
    conn5 = sqlite3.connect(DB)
    c5 = conn5.cursor()
    c5.execute("SELECT id, status, data FROM execution_entity ORDER BY id DESC LIMIT 1")
    latest = c5.fetchone()
    conn5.close()
    
    if latest:
        ex_id, st, ex_data = latest
        latest_detail = "#" + str(ex_id) + " " + str(st)
        if ex_data:
            ed = json.loads(ex_data)
            rd = ed.get('resultData',{}).get('runData',{})
            node_lines = []
            for nname, ndata in rd.items():
                if ndata and ndata[0]:
                    items = ndata[0].get('data',{}).get('main',[[]])[0]
                    has_out = bool(items and items[0])
                    txt = ""
                    if has_out:
                        sample = items[0].get('json',{})
                        for fld in ['text','content','tg_post','postText','title','score']:
                            if fld in sample:
                                txt = str(sample[fld])[:50]
                                break
                    node_lines.append(("OK " if has_out else "NO ") + nname + ": " + txt)
            latest_detail += "\n" + "\n".join(node_lines)
            err = ed.get('error')
            if err:
                latest_detail += "\nERR: " + str(err)[:150]
except Exception as e:
    latest_detail = "parse err: " + str(e)

# Send report
nr_str = "\n".join(node_report[:20])
tg(
    "<b>DEEP DIAGNOSIS</b>\n\n"
    "<b>Узлы n8n:</b>\n" + nr_str[:800] +
    "\n\n<b>Фиксы:</b> " + (", ".join(fixes) if fixes else "нет") +
    "\n<b>Webhook:</b> " + ("OK" if webhook_ok else "FAIL") +
    "\n\n<b>Последний exec:</b>\n" + latest_detail[:800]
)
print("DONE. fixes=" + str(fixes))
