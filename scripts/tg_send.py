#!/usr/bin/env python3
"""Grandvest Publisher v4 - с подтверждением публикации в канале"""
import os, sys, json, urllib.request, urllib.error, urllib.parse
from datetime import datetime

bot_token = os.environ.get("BOT_TOKEN", "")
chat_id = os.environ.get("CHAT_ID", "")
admin_chat = "5340000158"

if not bot_token or not chat_id:
    print("ERROR: BOT_TOKEN or CHAT_ID not set")
    sys.exit(1)

message = os.environ.get("MSG", "")
image_url = os.environ.get("IMG", "")
source_url = os.environ.get("SOURCE_URL", "")
source_name = os.environ.get("SOURCE_NAME", "")
parser_name = os.environ.get("PARSER_NAME", "")

event_path = os.environ.get("GITHUB_EVENT_PATH", "")
if event_path and os.path.exists(event_path):
    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)
    inputs = event.get("inputs", {})
    message = inputs.get("message", message)
    image_url = inputs.get("image_url", image_url)
    source_url = inputs.get("source_url", source_url)
    source_name = inputs.get("source_name", source_name)
    parser_name = inputs.get("parser_name", parser_name)

print(f"Message: {len(message)} chars | Image: {bool(image_url)} | Source: {source_name}")

if not message:
    print("ERROR: empty message")
    sys.exit(1)

msk_now = (datetime.utcnow()).strftime("%d.%m.%Y %H:%M") + " МСК"

def send_tg(payload, endpoint="sendMessage"):
    url = f"https://api.telegram.org/bot{bot_token}/{endpoint}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read().decode("utf-8"))
            if result.get("ok"):
                return result.get("result", {}).get("message_id")
            return None
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:100]}")
        return None

# Отправляем пост в канал
msg_id = None
if image_url:
    msg_id = send_tg({
        "chat_id": chat_id, "photo": image_url,
        "caption": message[:1024], "parse_mode": "HTML"
    }, "sendPhoto")
    if not msg_id:
        # Retry без parse_mode
        msg_id = send_tg({
            "chat_id": chat_id, "photo": image_url,
            "caption": message[:1024]
        }, "sendPhoto")
    if not msg_id:
        # Fallback: текст без фото
        msg_id = send_tg({"chat_id": chat_id, "text": message[:4096]}, "sendMessage")
else:
    msg_id = send_tg({
        "chat_id": chat_id, "text": message[:4096], "parse_mode": "HTML"
    }, "sendMessage")
    if not msg_id:
        msg_id = send_tg({"chat_id": chat_id, "text": message[:4096]}, "sendMessage")

if msg_id:
    print(f"SUCCESS! message_id={msg_id}")

    # Формируем ссылку на пост в канале
    # chat_id вида -1001234567890 → канал @username
    channel_handle = "grandvest_realty"
    post_link = f"https://t.me/{channel_handle}/{msg_id}"

    # Уведомление администратору — ПОСТ ОПУБЛИКОВАН
    notify = (
        f"✅ <b>ПОСТ ОПУБЛИКОВАН в @grandvest_realty</b>\n\n"
        f"🔗 <a href='{post_link}'>Открыть пост в канале</a>\n\n"
        f"⏰ Время публикации: {msk_now}\n"
        f"📡 Парсер: {parser_name or 'Парсер Telegram'}\n"
        f"📌 Источник: {source_name or '—'}\n"
    )
    if source_url:
        notify += f"🔗 Источник: <a href='{source_url}'>{source_url[:50]}</a>\n"
    notify += f"🖼 Картинка: {'да' if image_url else 'нет'} | 📝 {len(message)} символов"

    send_tg({
        "chat_id": admin_chat,
        "text": notify,
        "parse_mode": "HTML",
        "disable_web_page_preview": False  # Показываем превью поста
    }, "sendMessage")

    # Логируем
    log_entry = {
        "time_msk": msk_now,
        "parser": parser_name or "unknown",
        "source_name": source_name,
        "source_url": source_url,
        "post_link": post_link,
        "msg_id": msg_id,
        "has_image": bool(image_url),
        "chars": len(message)
    }
    try:
        import os as _os
        log_file = "/data/published_log.json"
        logs = []
        if _os.path.exists(log_file):
            with open(log_file) as f: logs = json.load(f)
        logs.append(log_entry)
        if len(logs) > 200: logs = logs[-150:]
        with open(log_file, "w") as f: json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Log error: {e}")
else:
    print("FAILED to publish!")
    send_tg({
        "chat_id": admin_chat,
        "text": f"❌ <b>Ошибка публикации!</b>\nВремя: {msk_now}\nПарсер: {parser_name}\nИсточник: {source_name}",
        "parse_mode": "HTML"
    }, "sendMessage")
    sys.exit(1)
