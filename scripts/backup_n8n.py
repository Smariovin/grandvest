#!/usr/bin/env python3
"""
Grandvest — безопасный бэкап n8n workflows.

ВАЖНО: этот скрипт ТОЛЬКО ЧИТАЕТ данные из n8n через GET-запросы.
Он не может ничего изменить, удалить или переписать в самом n8n —
используется только метод GET к n8n REST API.

Сохраняет JSON каждого воркфлоу в папку backups/ с датой в имени файла.
Хранит только последние KEEP_LAST копий на каждый воркфлоу, более старые
версии бэкапа удаляются (удаляются только сами файлы-бэкапы в этом
репозитории, реальная система n8n не затрагивается никак).
"""

import os
import json
import glob
import datetime
import urllib.request
import urllib.error

N8N_BASE_URL = "http://85.239.61.157:5678/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
BACKUP_DIR = "backups"
KEEP_LAST = 14

if not API_KEY:
    print("ОШИБКА: переменная окружения N8N_API_KEY не задана")
    raise SystemExit(1)

os.makedirs(BACKUP_DIR, exist_ok=True)


def n8n_get(path):
    """Только GET-запросы к n8n API. Никаких PUT/POST/DELETE."""
    req = urllib.request.Request(
        f"{N8N_BASE_URL}{path}",
        headers={"X-N8N-API-KEY": API_KEY, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def safe_name(name):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


def main():
    try:
        data = n8n_get("/workflows")
    except urllib.error.URLError as e:
        print(f"ОШИБКА подключения к n8n: {e}")
        raise SystemExit(1)

    workflows = data.get("data", [])
    if not workflows:
        print("Воркфлоу не найдены — возможно, изменился формат ответа API")
        raise SystemExit(1)

    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    saved = []

    for wf in workflows:
        wf_id = wf.get("id")
        name = safe_name(wf.get("name", "unnamed"))

        # Получаем полную версию воркфлоу (со всеми узлами) отдельным GET-запросом
        try:
            full_wf = n8n_get(f"/workflows/{wf_id}")
        except urllib.error.URLError as e:
            print(f"Не удалось получить детали воркфлоу {name} ({wf_id}): {e}")
            continue

        filename = os.path.join(BACKUP_DIR, f"{name}_{wf_id}_{date_str}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(full_wf, f, ensure_ascii=False, indent=2)
        print(f"Сохранено: {filename}")
        saved.append(filename)

        # Ротация: оставляем только последние KEEP_LAST копий этого воркфлоу
        pattern = os.path.join(BACKUP_DIR, f"{name}_{wf_id}_*.json")
        existing = sorted(glob.glob(pattern))
        if len(existing) > KEEP_LAST:
            for old_file in existing[:-KEEP_LAST]:
                os.remove(old_file)
                print(f"Удалена старая копия бэкапа: {old_file}")

    print(f"\nГотово. Забэкаплено воркфлоу: {len(saved)}")


if __name__ == "__main__":
    main()
