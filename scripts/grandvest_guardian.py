#!/usr/bin/env python3
"""Final RSS restore - URL fix + parser restore + dedup reset + run"""
import sqlite3, json, subprocess, time, urllib.request, urllib.parse, os, http.cookiejar

DB = "/opt/n8n/n8n_data/database.sqlite"
BOT = os.environ.get("TG_BOT", "")
CHAT = "5340000158"
RSS_WF_ID = "SIPnV2mqmgMqUkLb"

def tg(msg):
    if not BOT: print(msg); return
    d = urllib.parse.urlencode({"chat_id": CHAT, "text": msg[:4096], "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request("https://api.telegram.org/bot" + BOT + "/sendMessage", data=d, method="POST"),
            timeout=15
        )
    except Exception as e:
        print("TG:", e)

URLS = {
    "HTTP Request":  "https://news.google.com/rss/search?q=%D0%BA%D0%BE%D0%BC%D0%BC%D0%B5%D1%80%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request1": "https://news.google.com/rss/search?q=%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%BE%D1%84%D0%B8%D1%81%D0%BE%D0%B2+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request2": "https://news.google.com/rss/search?q=%D1%81%D0%BA%D0%BB%D0%B0%D0%B4%D1%8B+%D0%B0%D1%80%D0%B5%D0%BD%D0%B4%D0%B0+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request3": "https://news.google.com/rss/search?q=%D1%82%D0%BE%D1%80%D0%B3%D0%BE%D0%B2%D0%B0%D1%8F+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C+%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request4": "https://news.google.com/rss/search?q=%D0%B4%D0%B5%D0%B2%D0%B5%D0%BB%D0%BE%D0%BF%D0%BC%D0%B5%D0%BD%D1%82+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request5": "https://news.google.com/rss/search?q=%D0%B8%D0%BD%D0%B2%D0%B5%D1%81%D1%82%D0%B8%D1%86%D0%B8%D0%B8+%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C&hl=ru&gl=RU&ceid=RU:ru",
    "HTTP Request10": "https://www.vedomosti.ru/rss/rubric/realty",
    "РИА Недвижимость": "https://realty.ria.ru/export/rss2/index.xml",
    "Циан": "https://www.cian.ru/rss/",
}

print("=== FINAL RSS RESTORE ===")
subprocess.run(["docker", "stop", "n8n"], capture_output=True, timeout=20)
time.sleep(3)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id=?", (RSS_WF_ID,))
row = cur.fetchone()
if not row:
    tg("ERROR: RSS workflow not found!")
    exit(1)

wf_id, wf_name, nodes_raw = row
nodes = json.loads(nodes_raw)
fixes = []

for n in nodes:
    name = n.get("name", "")
    ntype = n.get("type", "")
    params = n.get("parameters", {})

    # 1. Восстанавливаем URL источников
    if ntype == "n8n-nodes-base.httpRequest" and name in URLS:
        params["url"] = URLS[name]
        params["method"] = "GET"
        params.pop("bodyContentType", None)
        params.pop("jsonBody", None)
        params.pop("specifyBody", None)
        n["parameters"] = params
        fixes.append("URL: " + name)
        print("URL fixed: " + name)

    # 2. Восстанавливаем парсер RSS (Code in JavaScript)
    elif ntype == "n8n-nodes-base.code" and name == "Code in JavaScript":
        code = params.get("jsCode", "")
        print("Current parser code (first 100): " + code[:100])
        # Если там нет парсинга XML - восстанавливаем
        if "<item>" not in code and "pubDate" not in code:
            parser = (
                "const items = [];\n"
                "const allInputs = $input.all();\n"
                "for (const input of allInputs) {\n"
                "  try {\n"
                "    const xmlStr = input.json.data || input.json.body || '';\n"
                "    if (!xmlStr || typeof xmlStr !== 'string') continue;\n"
                "    const itemMatches = xmlStr.match(/<item[^>]*>([\\s\\S]*?)<\\/item>/g) || [];\n"
                "    for (const itemXml of itemMatches) {\n"
                "      const titleMatch = itemXml.match(/<title>(?:<!\\[CDATA\\[)?(.*?)(?:\\]\\]>)?<\\/title>/s);\n"
                "      const linkMatch = itemXml.match(/<link>(.*?)<\\/link>/s) || itemXml.match(/<guid[^>]*>(.*?)<\\/guid>/s);\n"
                "      const descMatch = itemXml.match(/<description>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?<\\/description>/s);\n"
                "      const pubMatch = itemXml.match(/<pubDate>(.*?)<\\/pubDate>/s);\n"
                "      const title = (titleMatch ? titleMatch[1] : '').trim().replace(/<[^>]+>/g, '');\n"
                "      const link = (linkMatch ? linkMatch[1] : '').trim();\n"
                "      const desc = (descMatch ? descMatch[1] : '').trim().replace(/<[^>]+>/g, '').substring(0, 500);\n"
                "      const pubDate = pubMatch ? pubMatch[1].trim() : '';\n"
                "      if (!title || title.length < 5) continue;\n"
                "      const text = (title + ' ' + desc).toLowerCase();\n"
                "      const kw = ['недвижимост','аренд','офис','склад','торгов','девелопм','инвестиц','ставк','вакантност','кв.м','бизнес','логистик'];\n"
                "      if (!kw.some(k => text.includes(k))) continue;\n"
                "      if (pubDate) {\n"
                "        const pub = new Date(pubDate);\n"
                "        const diffH = (Date.now() - pub) / 3600000;\n"
                "        if (diffH > 48) continue;\n"
                "      }\n"
                "      items.push({ json: { title, link, description: desc, source: link, pub_date: pubDate, text: title + '. ' + desc } });\n"
                "    }\n"
                "  } catch(e) { console.log('Parse err:', e.message); }\n"
                "}\n"
                "console.log('Parsed items:', items.length);\n"
                "return items.slice(0, 20);"
            )
            params["jsCode"] = parser
            n["parameters"] = params
            fixes.append("Parser restored")
            print("Parser restored!")

    # 3. Дедупликация (Code in JavaScript3)
    elif ntype == "n8n-nodes-base.code" and name == "Code in JavaScript3":
        code = params.get("jsCode", "")
        if "require(" in code and "fs" in code:
            dedup = (
                "const items = $input.all();\n"
                "const sd = $getWorkflowStaticData('global');\n"
                "if (!sd.publishedTitles) sd.publishedTitles = [];\n"
                "const unique = [];\n"
                "for (const item of items) {\n"
                "  const t = (item.json.title || '').trim().toLowerCase().substring(0, 80);\n"
                "  if (!t) continue;\n"
                "  if (!sd.publishedTitles.some(p => p.substring(0, 80) === t)) unique.push(item);\n"
                "  else console.log('Dup:', t.substring(0, 40));\n"
                "}\n"
                "if (sd.publishedTitles.length > 500) sd.publishedTitles = sd.publishedTitles.slice(-300);\n"
                "console.log('Dedup: in=' + items.length + ' out=' + unique.length);\n"
                "return unique.slice(0, 1);"
            )
            params["jsCode"] = dedup
            n["parameters"] = params
            fixes.append("Dedup3 restored")
            print("Dedup3 restored")

    # 4. Запись дедупликации (Code in JavaScript4)
    elif ntype == "n8n-nodes-base.code" and name == "Code in JavaScript4":
        code = params.get("jsCode", "")
        if "require(" in code and "fs" in code:
            write = (
                "const item = $input.first().json;\n"
                "const t = (item.title || item.text || '').trim().toLowerCase().substring(0, 80);\n"
                "if (t) {\n"
                "  const sd = $getWorkflowStaticData('global');\n"
                "  if (!sd.publishedTitles) sd.publishedTitles = [];\n"
                "  if (!sd.publishedTitles.includes(t)) sd.publishedTitles.push(t);\n"
                "}\n"
                "return [$input.first()];"
            )
            params["jsCode"] = write
            n["parameters"] = params
            fixes.append("Write4 restored")
            print("Write4 restored")

# Сброс StaticData
try:
    cur.execute(
        "UPDATE workflow_static_data SET value=? WHERE workflowId=? AND type=?",
        (json.dumps({"publishedTitles": []}), RSS_WF_ID, "global")
    )
    fixes.append("StaticData reset")
    print("StaticData reset")
except Exception as e:
    print("StaticData err: " + str(e))

cur.execute(
    "UPDATE workflow_entity SET nodes=?, active=1 WHERE id=?",
    (json.dumps(nodes, ensure_ascii=False), wf_id)
)
conn.commit()
conn.close()
print("Fixes: " + str(fixes))

# Рестарт и запуск
subprocess.run(["docker", "start", "n8n"], capture_output=True, timeout=20)
for _ in range(15):
    time.sleep(4)
    try:
        urllib.request.urlopen("http://localhost:5678/healthz", timeout=5)
        print("n8n UP!")
        break
    except:
        pass

time.sleep(3)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId": "admin@grandvest.ru", "password": "Grandvest2026!"}).encode()
exec_id = None
try:
    opener.open(urllib.request.Request("http://localhost:5678/rest/login",
        data=ld, headers={"Content-Type": "application/json"}, method="POST"), timeout=10)
    rr = urllib.request.Request(
        "http://localhost:5678/rest/workflows/" + RSS_WF_ID + "/run",
        data=json.dumps({"runData": {}, "startNodes": [], "destinationNode": ""}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with opener.open(rr, timeout=30) as r:
        resp = json.loads(r.read())
    exec_id = resp.get("data", {}).get("executionId") or resp.get("executionId", "?")
    print("RSS started: " + str(exec_id))
except Exception as e:
    print("Run err: " + str(e)[:80])

lines = ["<b>RSS FULLY RESTORED</b>", ""]
lines.append("<b>Исправлено:</b>")
lines += ["• " + f for f in fixes]
lines += [
    "",
    "<b>Источники (9 штук):</b>",
    "• Google News x6 (ком.недвижимость, аренда офисов, склады, торговая, девелопмент, инвестиции)",
    "• Ведомости RSS",
    "• РИА Недвижимость",
    "• Циан",
    "",
    "exec_id=" + str(exec_id),
    "Жди 90 сек — пост в @grandvest_realty!"
]
tg("\n".join(lines))
print("DONE")
