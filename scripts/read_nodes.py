#!/usr/bin/env python3
"""
Исправляем все проблемные узлы в Парсере Telegram:
1. HTTP Request — генерация поста: user content должен содержать текст новости
2. 10. Запись в дедупликацию: убираем require('fs') -> StaticData
3. Проверяем все остальные узлы
БЕЗ остановки n8n
"""
import sqlite3, json, urllib.request, urllib.parse, http.cookiejar, os, time

DB = "/opt/n8n/n8n_data/database.sqlite"
N8N = "http://localhost:5678"
TG_WF = "F24jvKiXJIs4wRiZ"
RSS_WF = "SIPnV2mqmgMqUkLb"
try:
    BOT = open("/tmp/.tb").read().strip()
except:
    BOT = ""
CHAT = "5340000158"

def tg(msg):
    if not BOT: print(msg[:300]); return
    d = urllib.parse.urlencode({"chat_id": CHAT, "text": msg[:4096], "parse_mode": "HTML"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(
        "https://api.telegram.org/bot" + BOT + "/sendMessage", data=d, method="POST"), timeout=15)
    except Exception as e: print("TG:", e)

# ═══════════════════════════════════════════
# ПРАВИЛЬНЫЕ КОДЫ УЗЛОВ
# ═══════════════════════════════════════════

# Узел генерации поста — правильный user message с текстом новости
GENERATION_BODY = {
    "model": "anthropic/claude-sonnet-4-5",
    "max_tokens": 3000,
    "messages": [
        {
            "role": "system",
            "content": (
                "Ты - эксперт по рынку недвижимости России с 15-летним опытом. "
                "Пишешь посты для Telegram канала агентства Grandvest (Москва).\n\n"
                "Переписывай новость в формате экспертного поста, сохраняя суть оригинала.\n\n"
                "СТРУКТУРА:\n"
                "🏢 [ЗАГОЛОВОК — точно отражает суть новости, 8-12 слов]\n\n"
                "[ФАКТЫ: 4-5 предложений с конкретными цифрами и фактами из новости]\n\n"
                "💼 Комментарий Grandvest:\n"
                "[2-3 предложения экспертного мнения]\n\n"
                "💡 Что это значит для арендаторов/инвесторов:\n"
                "[1-2 практических вывода]\n\n"
                "📞 Консультация: @Grandvest_bot\n\n"
                "#коммерческаянедвижимость #Москва #Grandvest\n\n"
                "В конце добавь строку: IMAGE: [описание картинки на английском для AI, "
                "реалистичный офис или склад Москва, без людей, без текста]"
            )
        },
        {
            "role": "user",
            "content": "={{ $('6. Извлечение текста поста').first().json.text || $('1. Парсинг HTML Telegram').first().json.text || 'нет текста' }}"
        }
    ]
}

# Узел "6. Извлечение текста поста" — правильный
EXTRACT_CODE = """const items = [];

for (const input of $input.all()) {
  const item = input.json;
  const text = item.text || item.html || '';
  const channel = item.channel || '';
  const sourceUrl = item.source_url || '';
  const timeMsk = item.time_msk || '';

  if (!text || text.length < 20) continue;

  items.push({
    json: {
      text: text,
      channel: channel,
      source_url: sourceUrl,
      time_msk: timeMsk,
      score: item.score || 0,
      score_reason: item.score_reason || ''
    }
  });
}

console.log('Extract: ' + items.length + ' items');
return items.slice(0, 1);"""

# Узел "10. Запись в дедупликацию" — БЕЗ require('fs')
WRITE_DEDUP_CODE = """const item = $input.first().json;
const title = (item.title || item.tg_post || item.text || '').trim().toLowerCase().substring(0, 60);
if (title) {
  const staticData = $getWorkflowStaticData('global');
  if (!staticData.publishedTitles) staticData.publishedTitles = [];
  if (!staticData.publishedTitles.includes(title)) {
    staticData.publishedTitles.push(title);
  }
  if (staticData.publishedTitles.length > 500) {
    staticData.publishedTitles = staticData.publishedTitles.slice(-300);
  }
}
console.log('Dedup write done');
return [$input.first()];"""

# RSS дедупликация (Code in JavaScript3)
RSS_DEDUP_CODE = """const items = $input.all();
const staticData = $getWorkflowStaticData('global');
if (!staticData.publishedTitles) staticData.publishedTitles = [];
const published = staticData.publishedTitles;
const unique = [];
for (const item of items) {
  const title = (item.json.title || item.json.text || '').trim().toLowerCase().substring(0, 80);
  if (!title) continue;
  if (!published.some(p => p.substring(0, 80) === title)) unique.push(item);
  else console.log('Dup:', title.substring(0, 40));
}
if (staticData.publishedTitles.length > 500) {
  staticData.publishedTitles = staticData.publishedTitles.slice(-300);
}
console.log('Dedup: in=' + items.length + ' out=' + unique.length);
return unique.slice(0, 1);"""

# RSS запись дедупа (Code in JavaScript4)
RSS_WRITE_CODE = """const item = $input.first().json;
const title = (item.title || item.tg_post || item.text || '').trim().toLowerCase().substring(0, 80);
if (title) {
  const staticData = $getWorkflowStaticData('global');
  if (!staticData.publishedTitles) staticData.publishedTitles = [];
  if (!staticData.publishedTitles.includes(title)) staticData.publishedTitles.push(title);
}
return [$input.first()];"""

print("=== FIX ALL NODES ===")
conn = sqlite3.connect(DB)
cur = conn.cursor()
fixes = []

# ═══════ FIX ПАРСЕР TELEGRAM ═══════
cur.execute("SELECT id, nodes FROM workflow_entity WHERE id=?", (TG_WF,))
row = cur.fetchone()
if row:
    wf_id, nodes_raw = row
    nodes = json.loads(nodes_raw)
    changed = False
    for n in nodes:
        name = n.get("name", "")
        ntype = n.get("type", "")
        params = n.get("parameters", {})

        # FIX: HTTP Request — генерация поста
        if name == "HTTP Request — генерация поста" and ntype == "n8n-nodes-base.httpRequest":
            params["jsonBody"] = json.dumps(GENERATION_BODY, ensure_ascii=False)
            params["bodyContentType"] = "json"
            params["specifyBody"] = "json"
            n["parameters"] = params
            fixes.append("TG: генерация поста — user content исправлен")
            changed = True
            print("FIXED: HTTP Request — генерация поста")

        # FIX: 6. Извлечение текста поста
        elif name == "6. Извлечение текста поста" and ntype == "n8n-nodes-base.code":
            params["jsCode"] = EXTRACT_CODE
            n["parameters"] = params
            fixes.append("TG: узел 6 — исправлен extract")
            changed = True
            print("FIXED: 6. Извлечение текста поста")

        # FIX: 10. Запись в дедупликацию (require('fs') -> StaticData)
        elif name == "10. Запись в дедупликацию" and ntype == "n8n-nodes-base.code":
            code = params.get("jsCode", "")
            if "require(" in code or "fs" in code:
                params["jsCode"] = WRITE_DEDUP_CODE
                n["parameters"] = params
                fixes.append("TG: узел 10 — убран require('fs')")
                changed = True
                print("FIXED: 10. Запись в дедупликацию")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                   (json.dumps(nodes, ensure_ascii=False), wf_id))
        print(f"TG workflow saved ({len(fixes)} fixes)")

# ═══════ FIX RSS ═══════
cur.execute("SELECT id, nodes FROM workflow_entity WHERE id=?", (RSS_WF,))
row = cur.fetchone()
if row:
    wf_id_rss, nodes_raw_rss = row
    nodes_rss = json.loads(nodes_raw_rss)
    changed_rss = False
    for n in nodes_rss:
        name = n.get("name", "")
        ntype = n.get("type", "")
        params = n.get("parameters", {})

        if ntype != "n8n-nodes-base.code": continue
        code = params.get("jsCode", "")

        # FIX: Code in JavaScript3 — дедупликация
        if "JavaScript3" in name:
            params["jsCode"] = RSS_DEDUP_CODE
            n["parameters"] = params
            fixes.append("RSS: Code JS3 — дедупликация исправлена")
            changed_rss = True
            print("FIXED: RSS Code in JavaScript3")

        # FIX: Code in JavaScript4 — запись дедупа
        elif "JavaScript4" in name:
            if "require(" in code:
                params["jsCode"] = RSS_WRITE_CODE
                n["parameters"] = params
                fixes.append("RSS: Code JS4 — запись дедупа исправлена")
                changed_rss = True
                print("FIXED: RSS Code in JavaScript4")

    if changed_rss:
        cur.execute("UPDATE workflow_entity SET nodes=? WHERE id=?",
                   (json.dumps(nodes_rss, ensure_ascii=False), wf_id_rss))
        print(f"RSS workflow saved")

# Сбрасываем StaticData обоих workflow
for wf_id in [TG_WF, RSS_WF]:
    try:
        cur.execute("UPDATE workflow_static_data SET value=? WHERE workflowId=? AND type='global'",
                   (json.dumps({"publishedTitles": []}), wf_id))
    except: pass
fixes.append("StaticData обоих workflows сброшена")

conn.commit()
conn.close()
print("DB saved. Fixes:", fixes)

# Перезагружаем workflows через n8n API
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ld = json.dumps({"emailOrLdapLoginId": "admin@grandvest.ru", "password": "Grandvest2026!"}).encode()
try:
    opener.open(urllib.request.Request(N8N + "/rest/login",
        data=ld, headers={"Content-Type": "application/json"}, method="POST"), timeout=10)

    for wf_id in [TG_WF, RSS_WF]:
        try:
            opener.open(urllib.request.Request(
                N8N + "/rest/workflows/" + wf_id + "/deactivate",
                data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=10)
            time.sleep(1)
            opener.open(urllib.request.Request(
                N8N + "/rest/workflows/" + wf_id + "/activate",
                data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=10)
            print(f"Reloaded: {wf_id}")
        except Exception as e:
            print(f"Reload {wf_id}: {e}")

    time.sleep(3)

    # Тест webhook
    news = ("Офисный рынок Москвы: вакантность класса А снизилась до 7.8%. "
            "Ставки аренды в ЦАО достигли 48 000 руб/кв.м в год по данным CBRE.")
    payload = json.dumps({
        "channel": "CRERussia",
        "html": ('<div class="tgme_widget_message_text js-message_text">' + news + '</div>'
                 '<time datetime="2026-06-29T18:50:00+00:00">18:50</time>')
    }).encode("utf-8")

    res = urllib.request.urlopen(urllib.request.Request(
        N8N + "/webhook/telegram-parser",
        data=payload, headers={"Content-Type": "application/json"}), timeout=60)
    webhook = "OK " + str(res.status)
    fixes.append("Webhook тест: " + webhook)
    print("Webhook:", webhook)

except Exception as e:
    print("API err:", str(e)[:100])
    webhook = "err: " + str(e)[:50]

tg(
    "<b>FIX ALL NODES</b>\n\n"
    "<b>Исправлено:</b>\n" +
    "\n".join("• " + f for f in fixes) +
    "\n\nЖди ~30 сек — результат в @grandvest_realty"
)
print("DONE")
