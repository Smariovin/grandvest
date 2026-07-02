#!/usr/bin/env python3
"""
Grandvest — безопасный бэкап n8n workflows.

ВАЖНО: этот скрипт ТОЛЬКО ЧИТАЕТ данные из n8n через GET-запросы.
Он не может ничего изменить, удалить или переписать в самом n8n.

Перед сохранением все известные форматы секретов (GitHub-токены,
OpenRouter-ключи, fal.ai-ключи, Telegram bot-токены) вычищаются из
текста — GitHub блокирует push с настоящими секретами (push protection),
и хранить живые ключи в бэкапах небезопасно в любом случае.

Сохраняет JSON каждого воркфлоу в папку backups/ с датой в имени файла.
Хранит только последние KEEP_LAST копий на каждый воркфлоу.
"""

import os
import re
import json
import glob
import datetime
import urllib.request
import urllib.error

N8N_BASE_URL = "http://85.239.61.157:5678/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
BACKUP_DIR = "backups"
KEEP_LAST = 14

# Известные форматы секретов, которые нужно вычистить перед сохранением
SECRET_PATTERNS = [
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"), "[REDACTED_OPENROUTER_KEY]"),
    (re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}:[a-f0-9]{32,}"), "[REDACTED_FAL_KEY]"),
    (re.compile(r"\d{8,10}:[A-Za-z0-9_-]{30,40}"), "[REDACTED_TELEGRAM_BOT_TOKEN]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[REDACTED_JWT]"),
]

if not API_KEY:
    print("ОШИБКА: переменная окружения N8N_API_KEY не задана")
    raise SystemExit(1)

os.makedirs(BACKUP_DIR, exist_ok=True)


def n8n_get(path):
    req = urllib.request.Request(
        f"{N8N_BASE_URL}{path}",
        headers={"X-N8N-API-KEY": API_KEY, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def safe_name(name):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


def redact_secrets(text):
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def main():
    try:
        data = n8n_get("/workflows")
    except urllib.error.URLError as e:
        print(f"ОШИБКА подключения к n8n: {e}")
        raise SystemExit(1)

    workflows = data.get("data", data if isinstance(data, list) else [])
    print(f"Получено воркфлоу: {len(workflows)}")

    if not workflows:
        print("Воркфлоу не найдены")
        raise SystemExit(1)

    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    saved = []

    for wf in workflows:
        wf_id = wf.get("id")
        name = safe_name(wf.get("name", "unnamed"))

        raw_json = json.dumps(wf, ensure_ascii=False, indent=2)
        clean_json = redact_secrets(raw_json)

        filename = os.path.join(BACKUP_DIR, f"{name}_{wf_id}_{date_str}.json")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(clean_json)
        print(f"Сохранено (секреты вычищены): {filename} ({os.path.getsize(filename)} байт)")
        saved.append(filename)

        pattern = os.path.join(BACKUP_DIR, f"{name}_{wf_id}_*.json")
        existing = sorted(glob.glob(pattern))
        if len(existing) > KEEP_LAST:
            for old_file in existing[:-KEEP_LAST]:
                os.remove(old_file)
                print(f"Удалена старая копия: {old_file}")

    print(f"\nГотово. Забэкаплено воркфлоу: {len(saved)}")


if __name__ == "__main__":
    main()
