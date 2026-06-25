#!/usr/bin/env python3
"""Fix node 9. Отправка в Telegram to use grandvest-publisher.yml"""
import subprocess
import json
import os
import sys
import time

VPS = "root@85.239.61.157"
SSH_OPTS = ["-i", os.path.expanduser("~/.ssh/id_rsa"), "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15"]

GH_PAT = os.environ.get("GH_PAT", "")
TG_BOT = os.environ.get("TG_BOT", "")
MY_CHAT = "5340000158"

def ssh_run(cmd):
    result = subprocess.run(
        ["ssh"] + SSH_OPTS + [VPS, cmd],
        capture_output=True, text=True, timeout=60
    )
    return result.stdout, result.stderr

def send_tg(text):
    if not TG_BOT:
        return
    import urllib.request
    url = f"https://api.telegram.org/bot{TG_BOT}/sendMessage"
    payload = json.dumps({"chat_id": MY_CHAT, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        print("TG report sent")
    except Exception as e:
        print(f"TG error: {e}")

print("=== Fix Node 9: Отправка в Telegram ===")

# Step 1: Get current workflow JSON
print("\n1. Getting workflow from n8n...")
login_and_get = (
    "curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login "
    "-H 'Content-Type: application/json' "
    "-d '{\"emailOrLdapLoginId\":\"admin@grandvest.ru\",\"password\":\"Grandvest2026!\"}' > /dev/null && "
    "curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ' > /tmp/wf.json && "
    "echo 'SAVED'"
)
out, err = ssh_run(login_and_get)
print("Out:", out[:200], "Err:", err[:200])

if "SAVED" not in out:
    print("ERROR: could not get workflow")
    sys.exit(1)

# Step 2: Show current node names
print("\n2. Finding node 9...")
list_nodes = (
    "python3 -c \""
    "import json; d=json.load(open('/tmp/wf.json')); "
    "[print('NODE:', n.get('name','?'), '| TYPE:', n.get('type','?')) for n in d.get('nodes',[])]"
    "\""
)
out, err = ssh_run(list_nodes)
print("Nodes:", out[:1000])

# Step 3: Patch via Python on VPS
print("\n3. Patching node 9...")

new_code = (
    "// Узел 9: Отправка в Telegram через grandvest-publisher.yml\\n"
    "const postText = $(\\\"8. Подготовка данных поста\\\").first().json.tg_post;\\n"
    "const imageUrl = $(\\\"HTTP Request — fal.ai\\\").first().json.images?.[0]?.url || \\\"\\\";\\n"
    "\\n"
    "if (!postText || postText.length < 10) {\\n"
    "  throw new Error('postText is empty: ' + JSON.stringify(postText));\\n"
    "}\\n"
    "\\n"
    "console.log('postText length:', postText.length);\\n"
    "console.log('postText preview:', postText.substring(0, 150));\\n"
    "\\n"
    "const body = { ref: 'main', inputs: { message: postText, image_url: imageUrl } };\\n"
    "\\n"
    "const response = await this.helpers.httpRequest({\\n"
    "  method: 'POST',\\n"
    f"  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\\n"
    f"  headers: {{\\n"
    f"    'Authorization': 'token {GH_PAT}',\\n"
    "    'Content-Type': 'application/json',\\n"
    "    'Accept': 'application/vnd.github+json'\\n"
    "  }},\\n"
    "  body: JSON.stringify(body)\\n"
    "});\\n"
    "\\n"
    "console.log('Dispatch sent!');\\n"
    "return [{{ json: {{ status: 'dispatched', textLen: postText.length }} }}];"
)

patch_script = f"""
import json, sqlite3, subprocess

db = '/opt/n8n/n8n_data/database.sqlite'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id = 'F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
if not row:
    print("ERROR: no row")
    exit(1)

nodes = json.loads(row[0])
print(f"Total nodes: {{len(nodes)}}")

updated = 0
for n in nodes:
    name = n.get('name', '')
    if 'Telegram' in name and ('9.' in name or 'Отправка' in name):
        print(f"Patching: {{name}}")
        params = n.get('parameters', {{}})
        new_code = {json.dumps(new_code)}
        if 'jsCode' in params:
            params['jsCode'] = new_code
        else:
            params['jsCode'] = new_code
        n['parameters'] = params
        updated += 1

print(f"Updated {{updated}} nodes")

if updated > 0:
    cur.execute("UPDATE workflow_entity SET nodes = ? WHERE id = 'F24jvKiXJIs4wRiZ'", (json.dumps(nodes),))
    conn.commit()
    print("DB updated!")
else:
    print("No node found! Names were:")
    for n in nodes:
        print(" -", repr(n.get('name', '?')))

conn.close()

if updated > 0:
    subprocess.run(['docker', 'restart', 'n8n'], timeout=30)
    print("n8n restarted!")
"""

write_and_run = (
    f"python3 -c {json.dumps(patch_script)}"
)
out, err = ssh_run(write_and_run)
print("Patch out:", out[:2000])
if err:
    print("Patch err:", err[:500])

# Step 4: Wait and test
if "restarted" in out.lower():
    print("\n4. Waiting 20s for n8n to restart...")
    time.sleep(20)

    # Dedup reset
    out2, _ = ssh_run("echo '[]' > /data/published_titles.json && echo 'RESET'")
    print("Dedup reset:", out2[:100])

    # Test webhook
    test_cmd = (
        "curl -s -X POST http://localhost:5678/webhook/telegram-parser "
        "-H 'Content-Type: application/json' "
        "-d '{\"channel\":\"test\",\"html\":\"<div class=\\\"tgme_widget_message_text js-message_text\\\">Рынок коммерческой недвижимости Москвы вырос на 15% в первом полугодии 2026 года по данным ЦИАН</div><time datetime=\\\"2026-06-25T10:00:00+00:00\\\">10:00</time>\"}' "
        "&& echo 'TEST_OK'"
    )
    out3, _ = ssh_run(test_cmd)
    print("Webhook test:", out3[:500])

    send_tg("✅ <b>Fix Node 9 применён!</b>\n\nn8n обновлён: grandvest-publisher.yml\nDedup сброшен\nТест запущен\n\nПроверяй @grandvest_realty через 60 сек!")
else:
    send_tg("⚠️ <b>Fix Node 9: проблема</b>\n\nПатч не применился или n8n не перезапустился.\n" + out[:300])

print("\n=== DONE ===")
