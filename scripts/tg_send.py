#!/usr/bin/env python3
"""
Grandvest Telegram Publisher v2
Публикует пост в канал @grandvest_realty
"""
import os, sys, json, urllib.request, urllib.error

bot_token = os.environ.get("BOT_TOKEN", "")
chat_id = os.environ.get("CHAT_ID", "")

if not bot_token or not chat_id:
    print("ERROR: BOT_TOKEN or CHAT_ID not set")
    sys.exit(1)

# Читаем из GITHUB_EVENT_PATH
message = ""
image_url = ""
event_path = os.environ.get("GITHUB_EVENT_PATH", "")
if event_path and os.path.exists(event_path):
    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)
    inputs = event.get("inputs", {})
    message = inputs.get("message", "")
    image_url = inputs.get("image_url", "")

if not message:
    message = os.environ.get("MSG", "")
if not image_url:
    image_url = os.environ.get("IMG", "")

print(f"Message length: {len(message)} chars")
print(f"Image: {image_url[:60] if image_url else 'none'}")

if not message:
    print("ERROR: message is empty")
    sys.exit(1)

# Telegram caption ограничен 1024 символами, text — 4096
if image_url:
    # Обрезаем caption до 1024
    caption = message[:1024]
    payload = {
        "chat_id": chat_id,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML"
    }
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
else:
    payload = {
        "chat_id": chat_id,
        "text": message[:4096],
        "parse_mode": "HTML"
    }
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok"):
            msg_id = result.get("result", {}).get("message_id", "?")
            print(f"SUCCESS! message_id={msg_id}")
        else:
            # Если HTML ошибка — пробуем без parse_mode
            desc = result.get("description", "")
            print(f"Telegram error: {desc}")
            if "parse" in desc.lower() or "html" in desc.lower():
                print("Retrying without parse_mode...")
                payload.pop("parse_mode", None)
                data2 = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                req2 = urllib.request.Request(url, data=data2, headers={"Content-Type": "application/json; charset=utf-8"})
                with urllib.request.urlopen(req2, timeout=30) as resp2:
                    result2 = json.loads(resp2.read().decode("utf-8"))
                    if result2.get("ok"):
                        print(f"SUCCESS (no HTML)! message_id={result2.get('result',{}).get('message_id','?')}")
                    else:
                        print(f"Still failed: {result2}")
                        sys.exit(1)
            else:
                sys.exit(1)
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print(f"HTTP {e.code}: {body}")
    # Если 400 — пробуем без parse_mode
    if e.code == 400:
        print("Retrying without parse_mode...")
        payload.pop("parse_mode", None)
        data2 = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req2 = urllib.request.Request(url, data=data2, headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req2, timeout=30) as resp2:
                result2 = json.loads(resp2.read().decode("utf-8"))
                if result2.get("ok"):
                    print(f"SUCCESS (retry)! message_id={result2.get('result',{}).get('message_id','?')}")
                else:
                    print(f"Retry failed: {result2}")
                    sys.exit(1)
        except Exception as e2:
            print(f"Retry error: {e2}")
            sys.exit(1)
    else:
        sys.exit(1)
