import subprocess, requests, time, json

BOT = "8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT = "5340000158"
report = []

def ssh(cmd):
    r = subprocess.run(['ssh','-o','StrictHostKeyChecking=no','root@85.239.61.157',cmd],
        capture_output=True, text=True, timeout=120)
    return (r.stdout + r.stderr).strip()

def tg(msg):
    try:
        requests.post(f'https://api.telegram.org/bot{BOT}/sendMessage',
            data={'chat_id':CHAT,'text':msg[:4000],'parse_mode':'HTML'},timeout=10)
    except: pass

# 1. Проверка n8n
out = ssh("docker ps | grep n8n | wc -l")
if out.strip() == '0':
    report.append('❌ n8n не запущен — перезапускаем')
    ssh('chown 1000:1000 /opt/n8n/n8n_data/database.sqlite && chmod 644 /opt/n8n/n8n_data/database.sqlite && docker restart n8n')
    time.sleep(20)
else:
    report.append('✅ n8n работает')

out = ssh("curl -s -o /dev/null -w '%{http_code}' http://localhost:5678/healthz")
report.append(f'📊 Healthcheck: {out}')

# 2. Патч через файл на сервере
patch_script = '''import sqlite3, json
DB = "/opt/n8n/n8n_data/database.sqlite"
conn = sqlite3.connect(DB)
c = conn.cursor()
c.execute("SELECT id, name, nodes FROM workflow_entity")
for wf_id, wf_name, nodes_raw in c.fetchall():
    try: nodes = json.loads(nodes_raw)
    except: continue
    changed = False
    for node in nodes:
        if node.get("name") == "2. Дедупликация входящих" and node.get("type") == "n8n-nodes-base.code":
            if "readFileSync" in node["parameters"].get("jsCode","") or "require" in node["parameters"].get("jsCode",""):
                node["parameters"]["jsCode"] = """const items = $input.all();
const unique = [];
const published = $getWorkflowStaticData("global").publishedTitles || [];
for (const item of items) {
  const title = item.json.title?.trim().toLowerCase();
  if (!title) continue;
  const titleShort = title.substring(0, 50);
  const hasSimilar = published.some(p => p.substring(0, 50) === titleShort);
  if (hasSimilar) continue;
  unique.push(item);
}
return unique.slice(0, 1);"""
                changed = True
                print("OK: дедупликация исправлена в", wf_name)
        # Node 9 uses grandvest-publisher.yml - do not reset
    if changed:
        c.execute("UPDATE workflow_entity SET nodes = ? WHERE id = ?", (json.dumps(nodes), wf_id))
conn.commit()
conn.close()
print("Патчи применены")
'''

# Записываем патч как файл на сервер и запускаем
import subprocess
with open('/tmp/patch.py', 'w') as f:
    f.write(patch_script)

subprocess.run(['scp','-o','StrictHostKeyChecking=no','/tmp/patch.py','root@85.239.61.157:/root/patch.py'],
    capture_output=True)
out = ssh("python3 /root/patch.py")
report.append(f'🔧 Патч:\n{out[:300]}')

# 3. Перезапуск
ssh("docker restart n8n")
time.sleep(25)
report.append('🔄 n8n перезапущен')

# 4. Активация workflow через API
login = ssh("curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login -H 'Content-Type: application/json' -d '{\"emailOrLdapLoginId\":\"admin@grandvest.ru\",\"password\":\"Grandvest2026!\"}' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('login ok' if d.get('data') else 'login fail')\"")
report.append(f'🔑 Логин: {login}')

act1 = ssh("curl -s -b /tmp/ck.txt -X POST 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ/activate' -H 'Content-Type: application/json' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('active:', d.get('active','?'))\"")
act2 = ssh("curl -s -b /tmp/ck.txt -X POST 'http://localhost:5678/rest/workflows/SIPnV2mqmgMqUkLb/activate' -H 'Content-Type: application/json' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('active:', d.get('active','?'))\"")
report.append(f'✅ Парсер: {act1}')
report.append(f'✅ RSS: {act2}')

# 5. Сброс дедупликации
ssh("echo '[]' > /data/published_titles.json 2>/dev/null; echo '[]' > /opt/n8n/n8n_data/published_titles.json 2>/dev/null; true")
report.append('🔄 Дедупликация сброшена')

# 6. Тест
time.sleep(5)
out = ssh("""curl -s -X POST http://localhost:5678/webhook/telegram-parser -H 'Content-Type: application/json' -d '{"channel":"arendator_ru","html":"<div class=\\"tgme_widget_message_text js-message_text\\" dir=\\"auto\\">Офисная недвижимость Москвы 2026: вакантность офисов достигла минимума за 10 лет по данным аналитиков</div><time datetime=\\"2026-06-25T10:00:00+00:00\\">10:00</time>"}'""")
report.append(f'🚀 Тест: {out}')

time.sleep(60)

# 7. Проверяем результат
check = ssh("curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=3'")
try:
    data = json.loads(check)
    execs = data.get('data',{}).get('data',[])
    report.append(f'📋 Executions: {len(execs)}')
    for e in execs[:2]:
        status = e.get('status','?')
        wf = e.get('workflowName','?')
        report.append(f'  • {wf}: {status}')
        if status == 'error':
            rd = e.get('data',{}).get('resultData',{}).get('runData',{})
            for node, runs in rd.items():
                for run in runs:
                    err = run.get('error')
                    if err:
                        report.append(f'    ❌ [{node}]: {str(err.get("message","?"))[:100]}')
except Exception as ex:
    report.append(f'📋 Ошибка парсинга: {str(ex)[:100]}')

text = '<b>🤖 Агент Grandvest</b>\n\n' + '\n'.join(report)
tg(text)
print(text)
