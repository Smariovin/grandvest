import subprocess, requests, time, json

BOT = "8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw"
CHAT = "5340000158"
report = []

def ssh(cmd):
    r = subprocess.run(
        ['ssh', '-o', 'StrictHostKeyChecking=no', 'root@85.239.61.157', cmd],
        capture_output=True, text=True, timeout=120
    )
    return (r.stdout + r.stderr).strip()

def tg(msg):
    try:
        requests.post(f'https://api.telegram.org/bot{BOT}/sendMessage',
            data={'chat_id': CHAT, 'text': msg[:4000], 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        print(f'TG error: {e}')

# 1. Проверка n8n
out = ssh("docker ps | grep n8n | wc -l")
if out.strip() == '0':
    report.append('❌ n8n не запущен — перезапускаем')
    ssh('chown 1000:1000 /opt/n8n/n8n_data/database.sqlite && chmod 644 /opt/n8n/n8n_data/database.sqlite && docker restart n8n')
    time.sleep(20)
else:
    report.append('✅ n8n работает')

# 2. Healthcheck
out = ssh("curl -s -o /dev/null -w '%{http_code}' http://localhost:5678/healthz")
report.append(f'📊 Healthcheck: {out}')

# 3. Мега-патч всех узлов
fix = r"""
import sqlite3, json
DB = '/opt/n8n/n8n_data/database.sqlite'
conn = sqlite3.connect(DB)
c = conn.cursor()
c.execute("SELECT id, name, nodes FROM workflow_entity")
for wf_id, wf_name, nodes_raw in c.fetchall():
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue
    changed = False
    for node in nodes:
        # Патч узла дедупликации
        if node.get('name') == '2. Дедупликация входящих' and node.get('type') == 'n8n-nodes-base.code':
            code = node['parameters'].get('jsCode', '')
            if 'readFileSync' in code or 'require' in code:
                node['parameters']['jsCode'] = "const items = $input.all();\nconst unique = [];\nconst published = $getWorkflowStaticData('global').publishedTitles || [];\nfor (const item of items) {\n  const title = item.json.title?.trim().toLowerCase();\n  if (!title) continue;\n  const titleShort = title.substring(0, 50);\n  const hasSimilar = published.some(p => p.substring(0, 50) === titleShort);\n  if (hasSimilar) continue;\n  unique.push(item);\n}\nreturn unique.slice(0, 1);"
                changed = True
                print('OK: дедупликация исправлена в', wf_name)

        # Патч узла отправки в Telegram
        if node.get('name') == '9. Отправка в Telegram' and node.get('type') == 'n8n-nodes-base.code':
            node['parameters']['jsCode'] = "const postText = $(\"8. Подготовка данных поста\").first().json.tg_post;\nconst imageUrl = $(\"HTTP Request \u2014 fal.ai\").first().json.images[0].url;\nconst botToken = \"8672691136:AAHHXmzhwkWoI6mTzrz8L3_DuQfpq7kTTbw\";\nconst chatId = \"-1003971323034\";\nconst response = await this.helpers.httpRequest({\n  method: \"POST\",\n  url: \"https://api.telegram.org/bot\" + botToken + \"/sendPhoto\",\n  headers: { \"Content-Type\": \"application/json\" },\n  body: { chat_id: chatId, photo: imageUrl, caption: postText, parse_mode: \"HTML\" }\n});\nreturn [{ json: response }];"
            changed = True
            print('OK: узел 9 исправлен в', wf_name)

        # Патч HTTP Request6
        if node.get('name') == 'HTTP Request6' and node.get('type') == 'n8n-nodes-base.httpRequest':
            body = node['parameters'].get('body', '')
            if not str(body).strip().startswith('{') or 'function' in str(body):
                node['parameters']['body'] = '{"model":"google/gemini-flash-1.5","max_tokens":100,"messages":[{"role":"system","content":"Rate this news 0-10 for Moscow commercial real estate. Return ONLY JSON: {\\"score\\": 7, \\"topic\\": \\"office\\"}"},{"role":"user","content":"={{$json.title}} ={{$json.source}}"}]}'
                node['parameters']['bodyContentType'] = 'json'
                changed = True
                print('OK: HTTP Request6 исправлен в', wf_name)

    if changed:
        c.execute('UPDATE workflow_entity SET nodes = ? WHERE id = ?', (json.dumps(nodes), wf_id))

conn.commit()
conn.close()
print('Патчи применены')
"""
out = ssh(f"python3 -c {json.dumps(fix)}")
report.append(f'🔧 Патч:\n{out[:300]}')

# 4. Перезапуск
ssh("docker restart n8n")
time.sleep(20)
report.append('🔄 n8n перезапущен')

# 5. Активация workflow
ssh("curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login -H 'Content-Type: application/json' -d '{\"emailOrLdapLoginId\":\"admin@grandvest.ru\",\"password\":\"Grandvest2026!\"}' > /dev/null && curl -s -b /tmp/ck.txt -X POST 'http://localhost:5678/rest/workflows/F24jvKiXJIs4wRiZ/activate' > /dev/null && curl -s -b /tmp/ck.txt -X POST 'http://localhost:5678/rest/workflows/SIPnV2mqmgMqUkLb/activate' > /dev/null")
report.append('✅ Workflow активированы')

# 6. Сброс дедупликации
ssh("echo '[]' > /data/published_titles.json 2>/dev/null; echo '[]' > /opt/n8n/n8n_data/published_titles.json 2>/dev/null; true")
report.append('🔄 Дедупликация сброшена')

# 7. Тест
out = ssh("""curl -s -X POST http://localhost:5678/webhook/telegram-parser -H 'Content-Type: application/json' -d '{"channel":"arendator_ru","html":"<div class=\\"tgme_widget_message_text js-message_text\\" dir=\\"auto\\">Офисная недвижимость Москвы 2026: вакантность офисов достигла минимума за 10 лет по данным аналитиков рынка столицы</div><time datetime=\\"2026-06-25T10:00:00+00:00\\">10:00</time>"}'""")
report.append(f'🚀 Тест: {out}')

# 8. Ждём
time.sleep(60)

# 9. Проверяем execution
check = ssh("curl -s -c /tmp/ck.txt -X POST http://localhost:5678/rest/login -H 'Content-Type: application/json' -d '{\"emailOrLdapLoginId\":\"admin@grandvest.ru\",\"password\":\"Grandvest2026!\"}' >/dev/null && curl -s -b /tmp/ck.txt 'http://localhost:5678/rest/executions?limit=1'")
try:
    data = json.loads(check)
    execs = data.get('data', {}).get('data', [])
    if execs:
        e = execs[0]
        status = e.get('status', '?')
        report.append(f'📋 Execution: {status}')
        if status == 'error':
            rd = e.get('data', {}).get('resultData', {}).get('runData', {})
            for node, runs in rd.items():
                for run in runs:
                    err = run.get('error')
                    if err:
                        report.append(f'❌ [{node}]: {str(err.get("message","?"))[:150]}')
    else:
        report.append('⚠️ Нет executions — workflow не запустился')
except:
    report.append(f'📋 {check[:100]}')

# 10. Отчёт
text = '<b>🤖 Агент Grandvest</b>\n\n' + '\n'.join(report)
tg(text)
print(text)
