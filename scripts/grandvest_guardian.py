#!/usr/bin/env python3
"""Guardian v3 — простой и надёжный"""
import sqlite3, json, subprocess, re, os, urllib.request, urllib.parse, datetime, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = '8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw'
MY_CHAT = '5340000158'
PAT = os.environ.get('GH_PAT', '')

def tg(msg):
    try:
        url = f'https://api.telegram.org/bot{BOT}/sendMessage'
        data = urllib.parse.urlencode({'chat_id': MY_CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data, method='POST'), timeout=10)
    except: pass

msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
print(f"Guardian v3 | {msk.strftime('%d.%m.%Y %H:%M')} MSK")

fixes = []

# 1. n8n health
try:
    urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
    print("n8n: OK")
except:
    print("n8n: DOWN — restarting")
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=40)
    time.sleep(20)
    fixes.append("n8n перезапущен")

# 2. Читаем SQLite и патчим узел 9
if not PAT:
    print("No PAT — skipping node9 patch")
else:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, name, nodes FROM workflow_entity")
    
    for wf_id, wf_name, nodes_raw in cur.fetchall():
        try: nodes = json.loads(nodes_raw)
        except: continue
        
        changed = False
        for n in nodes:
            name = n.get('name', '')
            params = n.get('parameters', {})
            code = params.get('jsCode', params.get('code', ''))
            
            # Узел 9 — проверяем токен
            is_node9 = ('Отправка' in name and 'Telegram' in name) or ('9.' in name and 'Telegram' in name)
            if is_node9 and 'grandvest-publisher' in code:
                bad_tokens = [t for t in re.findall(r'ghp_[A-Za-z0-9]{10,}', code) if t != PAT]
                if bad_tokens:
                    for bad in bad_tokens:
                        code = code.replace(bad, PAT)
                    params['jsCode'] = code
                    params.pop('code', None)
                    n['parameters'] = params
                    changed = True
                    fixes.append(f"[{wf_name}] Node9 token fixed")
                    print(f"Fixed bad tokens in node9: {[t[:12] for t in bad_tokens]}")
        
        if changed:
            cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                       (json.dumps(nodes, ensure_ascii=False), wf_id))
    
    conn.commit()
    conn.close()

# 3. Dedup файл
try:
    with open('/data/published_titles.json') as f:
        dedup = json.load(f)
    count = len(dedup)
    if count > 300:
        with open('/data/published_titles.json', 'w') as f:
            json.dump(dedup[-100:], f, ensure_ascii=False)
        fixes.append(f"Dedup очищен: {count}→100")
        print(f"Dedup cleaned: {count}→100")
    else:
        print(f"Dedup: {count} items OK")
except FileNotFoundError:
    os.makedirs('/data', exist_ok=True)
    with open('/data/published_titles.json', 'w') as f: json.dump([], f)
    print("Dedup file created")
except Exception as e:
    print(f"Dedup error: {e}")

# 4. Отчёт только если были починки
if fixes:
    tg(f"✅ <b>Guardian v3</b>\n" + '\n'.join(f"• {f}" for f in fixes) + f"\n\n🕐 {msk.strftime('%H:%M')} МСК")
    print(f"Fixes: {fixes}")
else:
    print("All OK — no fixes needed")
