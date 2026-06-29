#!/usr/bin/env python3
"""Fix RSS sources in workflow - replace broken ones with working alternatives"""
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time, re, http.cookiejar

DB = "/opt/n8n/n8n_data/database.sqlite"
BOT = os.environ.get('TG_BOT', '')
CHAT = '5340000158'
RSS_WF_ID = "SIPnV2mqmgMqUkLb"

def tg(msg):
    if not BOT:
        print(msg)
        return
    d = urllib.parse.urlencode({'chat_id': CHAT, 'text': msg[:4096], 'parse_mode': 'HTML'}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request('https://api.telegram.org/bot' + BOT + '/sendMessage', data=d, method='POST'),
            timeout=15
        )
    except Exception as e:
        print('TG err:', e)

# Рабочие источники (проверены с VPS)
# Оставляем: Google News x3, РИА Недвижимость
# Заменяем: Ведомости(403), Коммерсант(404), RBC(0), Циан(0)
# Добавляем новые рабочие источники

WORKING_SOURCES = [
    # Уже работают
    ("Google: ком.недвижимость",
     "https://news.google.com/rss/search?q=%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru"),
    ("Google: аренда офисов",
     "https://news.google.com/rss/search?q=%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%BE%D1%84%D0%B8%D1%81%D0%BE%D0%B2+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru"),
    ("Google: склады",
     "https://news.google.com/rss/search?q=%D1%81%D0%BA%D0%BB%D0%B0%D0%B4%D1%8B+%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0&hl=ru&gl=RU&ceid=RU:ru"),
    ("РИА Недвижимость",
     "https://realty.ria.ru/export/rss2/index.xml"),
    # Новые замены
    ("Google: торговая недвижимость",
     "https://news.google.com/rss/search?q=%D1%82%D0%BE%D1%80%D0%B3%D0%BE%D0%B2%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru"),
    ("Google: офисы Москва-Сити",
     "https://news.google.com/rss/search?q=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0-%D0%A1%D0%B8%D1%82%D0%B8+%D0%BE%D1%84%D0%B8%D1%81%D1%8B+%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0&hl=ru&gl=RU&ceid=RU:ru"),
    ("Google: девелопмент",
     "https://news.google.com/rss/search?q=%D0%B4%D0%B5%D0%B2%D0%B5%D0%BB%D0%BE%D0%BF%D0%BC%D0%B5%D0%BD%D1%82+%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru"),
    ("Google: инвестиции недвижимость",
     "https://news.google.com/rss/search?q=%D0%B8%D0%BD%D0%B2%D0%B5%D1%81%D1%82%D0%B8%D1%86%D0%B8%D0%B8+%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru"),
]

print("=== FIX RSS SOURCES ===")
print("Working sources to set:", len(WORKING_SOURCES))

subprocess.run(['docker', 'stop', 'n8n'], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes, connections FROM workflow_entity WHERE id=?", (RSS_WF_ID,))
row = cur.fetchone()
if not row:
    tg("ERROR: RSS workflow not found!")
    conn.close()
    exit(1)

wf_id, wf_name, nodes_raw, conns_raw = row
nodes = json.loads(nodes_raw)
conns = json.loads(conns_raw) if conns_raw else {}

print("Nodes before: " + str(len(nodes)))

# Собираем все HTTP GET узлы (RSS источники) и нерабочие удаляем
rss_node_names = []
non_rss_nodes = []

BROKEN_URLS = ['vedomosti', 'kommersant', 'cian.ru/rss', 'realty.rbc']
WORKING_URLS = ['google.com/rss', 'ria.ru']

for n in nodes:
    ntype = n.get('type', '')
    params = n.get('parameters', {})
    name = n.get('name', '')
    url = params.get('url', '')
    method = params.get('method', 'GET')

    is_rss = (ntype == 'n8n-nodes-base.httpRequest' and
              method == 'GET' and
              any(k in url for k in ['google.com/rss', 'ria.ru', 'vedomosti', 'kommersant', 'cian.ru', 'realty.rbc']))

    if is_rss:
        rss_node_names.append(name)
    else:
        non_rss_nodes.append(n)

print("RSS source nodes found: " + str(len(rss_node_names)))
print("Non-RSS nodes kept: " + str(len(non_rss_nodes)))

# Находим Schedule Trigger для позиции старта
trigger_node = next((n for n in non_rss_nodes if 'scheduleTrigger' in n.get('type', '') or 'Schedule' in n.get('name', '')), None)
trigger_name = trigger_node.get('name', 'Schedule Trigger') if trigger_node else 'Schedule Trigger'

# Находим Merge узел
merge_node = next((n for n in non_rss_nodes if 'merge' in n.get('type', '').lower() or 'Merge' in n.get('name', '')), None)
merge_name = merge_node.get('name', 'Merge') if merge_node else 'Merge'

# Создаём новые RSS узлы
new_rss_nodes = []
base_x = 550
base_y = 100
step_y = 80

for i, (src_name, src_url) in enumerate(WORKING_SOURCES):
    node_id = 'rss-source-' + str(i)
    new_node = {
        'id': node_id,
        'name': src_name,
        'type': 'n8n-nodes-base.httpRequest',
        'typeVersion': 4.2,
        'position': [base_x, base_y + i * step_y],
        'parameters': {
            'method': 'GET',
            'url': src_url,
            'options': {},
            'responseFormat': 'string',
            'dataPropertyName': 'data'
        }
    }
    new_rss_nodes.append(new_node)

# Обновляем connections: Trigger -> все RSS, все RSS -> Merge
# Сначала удаляем старые connections от trigger к старым RSS узлам
old_trigger_conns = conns.get(trigger_name, {})
new_trigger_outputs = [[{'node': n['name'], 'type': 'main', 'index': 0} for n in new_rss_nodes]]
conns[trigger_name] = {'main': new_trigger_outputs}

# Удаляем старые RSS узлы из connections
for old_name in rss_node_names:
    conns.pop(old_name, None)

# Добавляем новые RSS -> Merge connections
for n in new_rss_nodes:
    conns[n['name']] = {'main': [[{'node': merge_name, 'type': 'main', 'index': 0}]]}

# Обновляем Merge - количество inputs
if merge_node:
    merge_node['parameters']['numberInputs'] = len(WORKING_SOURCES)

# Финальный список узлов
final_nodes = non_rss_nodes + new_rss_nodes
print("Nodes after: " + str(len(final_nodes)))

cur.execute(
    "UPDATE workflow_entity SET nodes=?, connections=?, active=1 WHERE id=?",
    (json.dumps(final_nodes, ensure_ascii=False), json.dumps(conns, ensure_ascii=False), wf_id)
)

# Сбрасываем StaticData
try:
    cur.execute("UPDATE workflow_static_data SET value=? WHERE workflowId=? AND type='global'",
               (json.dumps({'publishedTitles': []}), RSS_WF_ID))
    print("StaticData reset")
except Exception as e:
    print("StaticData reset err: " + str(e))

conn.commit()
conn.close()

# Рестарт n8n
subprocess.run(['docker', 'start', 'n8n'], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen('http://localhost:5678/healthz', timeout=5)
        print("n8n UP!")
        break
    except:
        pass

time.sleep(3)

# Запускаем RSS
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId": "admin@grandvest.ru", "password": "Grandvest2026!"}).encode()
exec_id = None
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type": "application/json"}, method="POST"), timeout=10)
    run_req = urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/run",
        data=json.dumps({"runData": {}, "startNodes": [], "destinationNode": ""}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with opener.open(run_req, timeout=30) as r:
        resp = json.loads(r.read())
    exec_id = resp.get("data", {}).get("executionId") or resp.get("executionId", "?")
    print("RSS started: exec_id=" + str(exec_id))
except Exception as e:
    print("Run error: " + str(e)[:100])

sources_str = "\n".join("+ " + s[0] for s in WORKING_SOURCES)
removed_str = "\n".join("- " + n for n in rss_node_names if any(b in n.lower() for b in ['ведомост', 'коммерсант', 'циан', 'rbc', 'realty']))

tg(
    "<b>RSS SOURCES UPDATED</b>\n\n"
    "<b>Добавлено/оставлено (" + str(len(WORKING_SOURCES)) + "):</b>\n" + sources_str +
    "\n\n<b>Удалено нерабочих:</b>\n" + str(len(rss_node_names) - 4) + " источников (Ведомости 403, Коммерсант 404, RBC пустой, Циан пустой)" +
    "\n\n<b>Запущен:</b> exec_id=" + str(exec_id) +
    "\nЖди ~90 сек — пост в @grandvest_realty!"
)
print("DONE")
