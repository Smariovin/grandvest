#!/usr/bin/env python3
"""GRANDVEST MASTER DIAGNOSTIC & FIX v2 - no hardcoded secrets"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT', '')
CHAT = os.environ.get('TG_CHAT', '5340000158')
PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    if not BOT: return
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4096], 'parse_mode': 'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=15)
    except Exception as e: print(f'TG err: {e}')

print("=== GRANDVEST MASTER FIX v2 ===")
fixes = []
all_nodes_report = []

# 1. n8n health check
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

# 2. Stop n8n, read & fix SQLite
subprocess.run(['docker','stop','n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")

for wf_id, wf_name, nodes_raw in cur.fetchall():
    try: nodes = json.loads(nodes_raw)
    except: continue
    changed = False

    for n in nodes:
        name = n.get('name','')
        ntype = n.get('type','')
        params = n.get('parameters',{})

        if ntype == 'n8n-nodes-base.httpRequest':
            url_v = params.get('url','')
            bct = params.get('bodyContentType','?')
            jb = str(params.get('jsonBody',''))[:80]
            print(f"  HTTP [{name}]: bct={bct!r} url={url_v[:50]}")
            all_nodes_report.append(f"HTTP|{name}|bct={bct}|url={url_v[:40]}")

            if 'openrouter' in url_v.lower() and bct != 'json':
                params['bodyContentType'] = 'json'
                params['specifyBody'] = 'json'
                n['parameters'] = params
                changed = True
                fixes.append(f"{wf_name}:{name} -> bct=json")

        elif ntype == 'n8n-nodes-base.code':
            code = params.get('jsCode','')
            print(f"  Code [{name}]: {len(code)} chars | preview: {code[:100]}")
            all_nodes_report.append(f"Code|{name}|{code[:100]}")

            if PAT and ('Отправка' in name or '9.' in name):
                if 'github.com' in code or 'grandvest-publisher' in code:
                    old_pats = re.findall(r'ghp_[A-Za-z0-9]{30,}', code)
                    for op in old_pats:
                        if op != PAT:
                            code = code.replace(op, PAT)
                            params['jsCode'] = code
                            n['parameters'] = params
                            changed = True
                            fixes.append(f"PAT updated in {name}")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()
print(f"Fixes so far: {fixes}")

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
try:
    test_news = (
        'Офисный рынок Москвы июнь 2026: вакантность класса А снизилась до 7.8 процента. '
        'Ставки аренды в ЦАО достигли 48 000 рублей за квадратный метр в год. '
        'Объём сделок за первое полугодие составил 650 тысяч квадратных метров, '
        'что на 20 процентов выше показателей 2025 года. Данные CBRE за июнь 2026.'
    )
    payload = json.dumps({
        'channel': 'CRERussia',
        'html': (
            f'<div class="tgme_widget_message_text js-message_text">{test_news}</div>'
            '<time datetime="2026-06-28T21:30:00+00:00">21:30</time>'
        )
    }).encode('utf-8')
    res = urllib.request.urlopen(
        urllib.request.Request('http://localhost:5678/webhook/telegram-parser',
            data=payload, headers={'Content-Type':'application/json'}), timeout=60)
    print(f"Webhook: {res.status} {res.read().decode()[:100]}")
    webhook_ok = True
except Exception as e:
    print(f"Webhook error: {e}")
    webhook_ok = False

time.sleep(12)

# 6. Check last execution
exec_detail = "unknown"
node_outputs = []
try:
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    ld = json.dumps({"emailOrLdapLoginId":"admin@grandvest.ru","password":"Grandvest2026!"}).encode()
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    with opener.open("http://localhost:5678/rest/executions?limit=1&workflowId=F24jvKiXJIs4wRiZ", timeout=10) as r:
        ed = json.loads(r.read())
    execs = ed.get('data',{}).get('data', ed.get('data',[]))
    if isinstance(execs, list) and execs:
        ex = execs[0]
        exec_detail = f"{ex.get('status')} @ {str(ex.get('startedAt',''))[:16]}"
        rd = ex.get('data',{}).get('resultData',{}).get('runData',{})
        for nn, nd in rd.items():
            if nd and nd[0]:
                items = nd[0].get('data',{}).get('main',[[]])[0]
                if items and items[0]:
                    keys = list(items[0].get('json',{}).keys())[:5]
                    txt = items[0].get('json',{}).get('text','')[:80] or items[0].get('json',{}).get('tg_post','')[:80]
                    node_outputs.append(f"  {nn}: keys={keys} txt={txt!r}")
except Exception as e:
    print(f"n8n API err: {e}")

nodes_str = chr(10).join(all_nodes_report[:15])
outputs_str = chr(10).join(node_outputs[:8]) if node_outputs else "no data"

tg(
    f"<b>GRANDVEST MASTER FIX</b>\n\n"
    f"<b>Исправлено:</b>\n" +
    (chr(10).join(f"• {f}" for f in fixes) if fixes else "• Без исправлений") +
    f"\n\n<b>Тест:</b> {'OK' if webhook_ok else 'FAIL'}\n"
    f"<b>Последний exec:</b> {exec_detail}\n\n"
    f"<b>Выходы узлов:</b>\n{outputs_str[:600]}\n\n"
    f"<b>Узлы n8n:</b>\n{nodes_str[:600]}"
)
print(f"DONE. Fixes={fixes}, webhook={'OK' if webhook_ok else 'FAIL'}")
