#!/usr/bin/env python3
"""
Grandvest Telegram Publisher
Reads message from GITHUB_EVENT_PATH (most reliable for multiline unicode text)
Falls back to MSG env var
"""
import os
import sys
import json
import urllib.request
import urllib.error

bot_token = os.environ.get("BOT_TOKEN", "")
chat_id = os.environ.get("CHAT_ID", "")

if not bot_token or not chat_id:
    print("ERROR: BOT_TOKEN or CHAT_ID not set")
    sys.exit(1)

# Primary: GITHUB_EVENT_PATH
message = ""
image_url = ""
event_path = os.environ.get("GITHUB_EVENT_PATH", "")
if event_path and os.path.exists(event_path):
    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)
    inputs = event.get("inputs", {})
    message = inputs.get("message", "")
    image_url = inputs.get("image_url", "")

# Fallback: env vars
if not message:
    message = os.environ.get("MSG", "")
if not image_url:
    image_url = os.environ.get("IMG", "")

print(f"Message length: {len(message)} chars")
print(f"First 150 chars: {message[:150]!r}")
print(f"Image URL: {image_url[:80] if image_url else 'none'}")

if not message:
    print("ERROR: message is empty")
    sys.exit(1)

api_base = f"https://api.telegram.org/bot{bot_token}"

if image_url:
    url = f"{api_base}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": image_url,
        "caption": message,
        "parse_mode": "HTML"
    }
else:
    url = f"{api_base}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(
    url,
    data=data,
    headers={"Content-Type": "application/json; charset=utf-8"}
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok"):
            msg_id = result.get("result", {}).get("message_id", "?")
            print(f"SUCCESS: message_id={msg_id}")
        else:
            print(f"Telegram API error: {result}")
            sys.exit(1)
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print(f"HTTP Error {e.code}: {body}")
    sys.exit(1)
