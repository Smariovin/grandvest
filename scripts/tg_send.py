#!/usr/bin/env python3
"""Grandvest Telegram Publisher v3 - с уведомлением об источнике"""
import os, sys, json, urllib.request, urllib.error, urllib.parse
from datetime import datetime

bot_token = os.environ.get("BOT_TOKEN", "")
chat_id = os.environ.get("CHAT_ID", "")
admin_chat = os.environ.get("ADMIN_CHAT", "5340000158")

if not bot_token or not chat_id:
    print("ERROR: BOT_TOKEN or CHAT_ID not set")
    sys.exit(1)

# Читаем данные из event
message = os.environ.get("MSG", "")
image_url = os.environ.get("IMG", "")
source_url = os.environ.get("SOURCE_URL", "")
source_name = os.environ.get("SOURCE_NAME", "")
source_date = os.environ.get("SOURCE_DATE", "")

event_path = os.environ.get("GITHUB_EVENT_PATH", "")
if event_path and os.path.exists(event_path):
    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)
    inputs = event.get("inputs", {})
    message = inputs.get("message", message)
    image_url = inputs.get("image_url", image_url)
    source_url = inputs.get("source_url", source_url)
    source_name = inputs.get("source_name", source_name)
    source_date = inputs.get("source_date", source_date)

print(f"Message: {len(message)} chars")
print(f"Image: {image_url[:60] if image_url else 'none'}")
print(f"Source: {source_name} | {source_url[:60] if source_url else 'none'}")

if not message:
    print("ERROR: empty message")
    sys.exit(1)

def send_tg(token, cid, payload):
    url_map = {
        'photo': f'https://api.telegram.org/bot{token}/sendPhoto',
        'text': f'https://api.telegram.org/bot{token}/sendMessage'
    }
    mode = 'photo' if payload.get('photo') else 'text'
    url = url_map[mode]
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read().decode("utf-8"))
            if result.get("ok"):
                return result.get("result", {}).get("message_id")
            else:
                return None, result.get("description", "?")
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:100]}"

# Отправляем пост в канал
now_msk = datetime.utcnow().strftime("%d.%m.%Y %H:%M") + " МСК"

if image_url:
    payload = {"chat_id": chat_id, "photo": image_url,
               "caption": message[:1024], "parse_mode": "HTML"}
    msg_id = send_tg(bot_token, chat_id, payload)
    if not msg_id:
        # Retry без parse_mode
        payload.pop("parse_mode")
        msg_id = send_tg(bot_token, chat_id, payload)
        if not msg_id:
            # Retry как текст
            payload2 = {"chat_id": chat_id, "text": message[:4096]}
            msg_id = send_tg(bot_token, chat_id, payload2)
else:
    payload = {"chat_id": chat_id, "text": message[:4096], "parse_mode": "HTML"}
    msg_id = send_tg(bot_token, chat_id, payload)
    if not msg_id:
        payload.pop("parse_mode")
        msg_id = send_tg(bot_token, chat_id, payload)

if msg_id:
    print(f"SUCCESS! message_id={msg_id}")
    
    # Логируем в файл для дневного отчёта
    import os as _os
    log_entry = {
        "time": now_msk,
        "source_name": source_name or "unknown",
        "source_url": source_url or "",
        "source_date": source_date or "",
        "msg_id": msg_id,
        "chars": len(message),
        "has_image": bool(image_url)
    }
    log_file = "/data/published_log.json"
    try:
        logs = []
        if _os.path.exists(log_file):
            with open(log_file) as f: logs = json.load(f)
        logs.append(log_entry)
        # Храним только последние 100 записей
        if len(logs) > 100: logs = logs[-100:]
        with open(log_file, "w") as f: json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Log error: {e}")
    
    # Уведомление в личку с источником
    notify = (
        f"✅ <b>Пост опубликован в @grandvest_realty</b>

"
        f"🕐 Время: {now_msk}
"
        f"📰 Источник: {source_name or 'не указан'}
"
    )
    if source_url:
        notify += f"🔗 Ссылка: {source_url}
"
    if source_date:
        notify += f"📅 Дата новости: {source_date}
"
    notify += f"
📝 {len(message)} символов | 🖼 Картинка: {'да' if image_url else 'нет'}"
    
    notif_payload = {"chat_id": admin_chat, "text": notify, "parse_mode": "HTML",
                     "disable_web_page_preview": True}
    data = json.dumps(notif_payload, ensure_ascii=False).encode("utf-8")
    notif_req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        urllib.request.urlopen(notif_req, timeout=10)
        print("Notification sent!")
    except Exception as e:
        print(f"Notify error: {e}")
else:
    print(f"FAILED to send")
    sys.exit(1)
