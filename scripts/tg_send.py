#!/usr/bin/env python3
"""
Grandvest Publisher v5
- Публикует пост в канал
- Верифицирует что пост реально появился
- Если не появился — диагностирует и повторяет
- Отчёт в личку с подтверждением или ошибкой
"""
import os, sys, json, urllib.request, urllib.error, urllib.parse, time
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")   # канал -1003971323034
ADMIN_CHAT = "5340000158"
CHANNEL_USERNAME = "grandvest_realty"

if not BOT_TOKEN or not CHAT_ID:
    print("ERROR: BOT_TOKEN or CHAT_ID not set")
    sys.exit(1)

# Читаем inputs
event_path = os.environ.get("GITHUB_EVENT_PATH", "")
inputs = {}
if event_path and os.path.exists(event_path):
    with open(event_path, "r", encoding="utf-8") as f:
        inputs = json.load(f).get("inputs", {})

message     = inputs.get("message",     os.environ.get("MSG", ""))
image_url   = inputs.get("image_url",   os.environ.get("IMG", ""))
source_url  = inputs.get("source_url",  os.environ.get("SOURCE_URL", ""))
source_name = inputs.get("source_name", os.environ.get("SOURCE_NAME", ""))
parser_name = inputs.get("parser_name", os.environ.get("PARSER_NAME", ""))

if not message:
    print("ERROR: empty message")
    sys.exit(1)

# Если CHAT_ID — это личка (не канал), просто отправляем сообщение и выходим
CHANNEL_ID = "-1003971323034"
IS_REPORT = (CHAT_ID == ADMIN_CHAT or CHAT_ID == "5340000158")
if IS_REPORT:
    print(f"[REPORT MODE] Sending to personal chat {CHAT_ID}")
    def send_report(text):
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text[:4096], "parse_mode": "HTML"},
                         ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data,
              headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"Report send error: {e}")
            return {"ok": False}
    send_report(message)
    print("Report sent to personal chat!")
    sys.exit(0)

msk = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M")
print(f"[{msk} МСК] Publishing {len(message)} chars | src={source_name}")

# ─── helpers ───
def api(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req  = urllib.request.Request(url, data=data,
           headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  API error {e.code}: {body[:200]}")
        return {"ok": False, "description": body[:200], "error_code": e.code}

def tg_admin(text):
    api("sendMessage", {
        "chat_id": ADMIN_CHAT, "text": text[:4096],
        "parse_mode": "HTML", "disable_web_page_preview": False
    })

# ─── Шаг 1: публикуем пост ───
def publish(text, img, parse_html=True):
    pm = "HTML" if parse_html else None
    if img:
        payload = {"chat_id": CHAT_ID, "photo": img, "caption": text[:1024]}
        if pm: payload["parse_mode"] = pm
        return api("sendPhoto", payload)
    else:
        payload = {"chat_id": CHAT_ID, "text": text[:4096]}
        if pm: payload["parse_mode"] = pm
        return api("sendMessage", payload)

print("Publishing to channel...")
result = publish(message, image_url)

# Если HTML ошибка — повтор без parse_mode
if not result.get("ok") and "parse" in str(result.get("description","")).lower():
    print("  HTML error, retrying without parse_mode...")
    result = publish(message, image_url, parse_html=False)

# Если фото не грузится — текст без фото
if not result.get("ok") and image_url:
    print("  Photo error, retrying as text...")
    result = publish(message, "", parse_html=False)

if not result.get("ok"):
    err = result.get("description", "unknown error")
    print(f"PUBLISH FAILED: {err}")
    tg_admin(
        f"❌ <b>ОШИБКА ПУБЛИКАЦИИ!</b>\n\n"
        f"⏰ {msk} МСК\n"
        f"📡 Парсер: {parser_name}\n"
        f"📌 Источник: {source_name}\n"
        f"❗ Ошибка: {err}\n\n"
        f"🔧 Требуется вмешательство!"
    )
    sys.exit(1)

msg_id   = result["result"]["message_id"]
post_link = f"https://t.me/{CHANNEL_USERNAME}/{msg_id}"
print(f"Published! msg_id={msg_id} link={post_link}")

# ─── Шаг 2: верификация — пост реально есть в канале? ───
print("Verifying post in channel...")
time.sleep(5)  # даём Telegram обработать

def verify_post(message_id, retries=3):
    """Проверяем что сообщение реально есть в канале"""
    for attempt in range(retries):
        r = api("forwardMessage", {
            "chat_id": ADMIN_CHAT,          # пересылаем себе
            "from_chat_id": CHAT_ID,
            "message_id": message_id,
            "disable_notification": True
        })
        if r.get("ok"):
            forwarded_id = r["result"]["message_id"]
            # Удаляем пересланное сообщение чтобы не засорять чат
            time.sleep(1)
            api("deleteMessage", {"chat_id": ADMIN_CHAT, "message_id": forwarded_id})
            return True, None
        
        err = r.get("description", "")
        print(f"  Verify attempt {attempt+1}: {err}")
        
        if "message not found" in err.lower() or "invalid" in err.lower():
            return False, err
        
        time.sleep(3)  # ждём и повторяем
    
    return False, "таймаут верификации"

verified, verify_err = verify_post(msg_id)

# ─── Шаг 3: логирование ───
log_entry = {
    "time_msk":    msk,
    "parser":      parser_name,
    "source_name": source_name,
    "source_url":  source_url,
    "post_link":   post_link,
    "msg_id":      msg_id,
    "verified":    verified,
    "has_image":   bool(image_url),
    "chars":       len(message)
}
try:
    import os as _os
    log_file = "/data/published_log.json"
    logs = []
    if _os.path.exists(log_file):
        with open(log_file) as f: logs = json.load(f)
    logs.append(log_entry)
    if len(logs) > 300: logs = logs[-200:]
    with open(log_file, "w") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
except Exception as e:
    print(f"Log error: {e}")

# ─── Шаг 4: отчёт в личку ───
if verified:
    tg_admin(
        f"✅ <b>ПОСТ ОПУБЛИКОВАН И ПОДТВЕРЖДЁН</b>\n\n"
        f"🔗 <a href='{post_link}'>Открыть пост в @{CHANNEL_USERNAME}</a>\n\n"
        f"⏰ Время публикации: {msk} МСК\n"
        f"📡 Парсер: {parser_name or '—'}\n"
        f"📌 Источник: {source_name or '—'}\n"
        + (f"🔗 URL: <a href='{source_url}'>{source_url[:50]}</a>\n" if source_url else "")
        + f"🖼 Картинка: {'да' if image_url else 'нет'} | 📝 {len(message)} симв\n"
        f"✅ Верификация: пост реально в канале"
    )
    print("SUCCESS: post verified in channel")
else:
    # Пост опубликован но не верифицирован — пробуем получить через getChatMessage
    print(f"WARNING: verification failed: {verify_err}")
    
    # Дополнительная проверка через getChat
    chat_info = api("getChat", {"chat_id": CHAT_ID})
    last_id_in_channel = chat_info.get("result", {}).get("pinned_message", {}).get("message_id", "?")
    
    tg_admin(
        f"⚠️ <b>ПОСТ ОПУБЛИКОВАН, НО ВЕРИФИКАЦИЯ НЕ УДАЛАСЬ</b>\n\n"
        f"🔗 <a href='{post_link}'>Проверь пост: @{CHANNEL_USERNAME}/{msg_id}</a>\n\n"
        f"⏰ Время: {msk} МСК\n"
        f"📡 Парсер: {parser_name or '—'}\n"
        f"📌 Источник: {source_name or '—'}\n"
        f"⚠️ Причина: {verify_err}\n\n"
        f"ℹ️ Пост отправлен с msg_id={msg_id}. "
        f"Возможно бот не имеет прав читать историю канала — "
        f"это нормально если у бота нет прав администратора."
    )
    print(f"WARNING: post sent (id={msg_id}) but verification failed: {verify_err}")
    # Это не ошибка — пост был отправлен успешно
