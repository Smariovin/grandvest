#!/usr/bin/env python3
"""
Grandvest — мониторинг системы.

ВАЖНО: этот скрипт ТОЛЬКО ЧИТАЕТ данные (n8n API, OpenRouter API)
и ТОЛЬКО ОТПРАВЛЯЕТ уведомление в Telegram при обнаружении проблемы.
Он НИКОГДА не пытается сам что-либо исправить, перезапустить,
изменить настройки n8n или воркфлоу. Это осознанное ограничение —
самостоятельные "агенты-чинильщики" уже создавали проблемы в этом
проекте раньше, поэтому починка остаётся исключительно за человеком.
"""

import os
import json
import datetime
import urllib.request
import urllib.error

N8N_BASE = "http://85.239.61.157:5678/api/v1"
N8N_KEY = os.environ.get("N8N_API_KEY")
GH_TOKEN = os.environ.get("REPO_PUSH_TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

STATE_FILE = "monitor/state.json"
WORKFLOWS = {
    "SIPnV2mqmqMqUkLb": "RSS",
    "F24jvKiXJIs4wRiZ": "Парсер Telegram",
}
WORK_HOUR_START = 8
WORK_HOUR_END = 21
STALL_THRESHOLD_MIN = 90  # если внутри рабочего окна нет успеха дольше этого — сигнал


def n8n_get(path):
    req = urllib.request.Request(
        f"{N8N_BASE}{path}",
        headers={"X-N8N-API-KEY": N8N_KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_alert(text):
    body = json.dumps({
        "ref": "main",
        "inputs": {
            "message": text,
            "image_url": "",
            "source_url": "",
            "source_name": "",
            "parser_name": "Монитор",
            "chat_id": "5340000158",
        },
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches",
        data=body,
        method="POST",
        headers={
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=15)


def moscow_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=3)


def main():
    if not N8N_KEY or not GH_TOKEN:
        print("ОШИБКА: не заданы N8N_API_KEY или REPO_PUSH_TOKEN")
        raise SystemExit(1)

    state = load_state()
    problems = []
    msk = moscow_now()

    # 1. Доступность n8n
    try:
        n8n_get("/workflows")
    except Exception as e:
        send_alert(f"🔴 <b>Мониторинг Grandvest</b>\n\nn8n недоступен!\nОшибка: {e}")
        print("n8n недоступен, отправлено предупреждение")
        return

    # 2-3. Новые ошибки и зависания по каждому воркфлоу
    for wf_id, label in WORKFLOWS.items():
        wf_state = state.setdefault(wf_id, {})

        # Новые ошибки
        try:
            err_data = n8n_get(f"/executions?workflowId={wf_id}&status=error&limit=10")
            errors = err_data.get("data", [])
        except Exception as e:
            problems.append(f"⚠️ {label}: не удалось проверить ошибки ({e})")
            errors = []

        last_seen_error = wf_state.get("last_error_id")
        is_first_run = last_seen_error is None
        new_errors = []
        if not is_first_run:
            for ex in errors:
                if str(ex.get("id")) == str(last_seen_error):
                    break
                new_errors.append(ex)
        if is_first_run and errors:
            print(f"{label}: первая проверка, запоминаю базовую точку без тревоги")
        if new_errors:
            problems.append(
                f"🔴 {label}: новых ошибок выполнения — {len(new_errors)}"
            )
        if errors:
            wf_state["last_error_id"] = errors[0].get("id")

        # Зависание — если рабочее окно и давно нет успеха
        if WORK_HOUR_START <= msk.hour < WORK_HOUR_END:
            try:
                ok_data = n8n_get(f"/executions?workflowId={wf_id}&status=success&limit=1")
                ok_list = ok_data.get("data", [])
                if ok_list:
                    started = ok_list[0].get("startedAt", "")
                    last_dt = datetime.datetime.fromisoformat(started.replace("Z", "+00:00")).replace(tzinfo=None)
                    gap_min = (datetime.datetime.utcnow() - last_dt).total_seconds() / 60
                    if gap_min > STALL_THRESHOLD_MIN:
                        problems.append(
                            f"🟡 {label}: нет успешных запусков уже {int(gap_min)} мин "
                            f"(в рабочее окно {WORK_HOUR_START}-{WORK_HOUR_END} МСК) — возможное зависание"
                        )
                else:
                    problems.append(f"🟡 {label}: ни одного успешного выполнения не найдено вообще")
            except Exception as e:
                problems.append(f"⚠️ {label}: не удалось проверить время последнего успеха ({e})")

        # Перегруженность — среднее время выполнения последних запусков
        try:
            recent = n8n_get(f"/executions?workflowId={wf_id}&limit=5")
            recent_list = recent.get("data", [])
            durations = []
            for ex in recent_list:
                started = ex.get("startedAt")
                stopped = ex.get("stoppedAt")
                if started and stopped:
                    s = datetime.datetime.fromisoformat(started.replace("Z", "+00:00"))
                    e_ = datetime.datetime.fromisoformat(stopped.replace("Z", "+00:00"))
                    durations.append((e_ - s).total_seconds())
            if durations:
                avg = sum(durations) / len(durations)
                if avg > 60:
                    problems.append(
                        f"🟡 {label}: среднее время выполнения выросло до {avg:.1f} сек "
                        f"(последние {len(durations)} запусков) — возможна перегрузка"
                    )
        except Exception as e:
            problems.append(f"⚠️ {label}: не удалось проверить время выполнения ({e})")

    # 4. Баланс OpenRouter
    if OPENROUTER_KEY:
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/credits",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                credits = json.load(r)
            d = credits.get("data", {})
            balance = float(d.get("total_credits", 0)) - float(d.get("total_usage", 0))
            if balance < 1:
                problems.append(f"🔴 КРИТИЧНО: баланс OpenRouter ${balance:.2f} — генерация постов скоро остановится!")
            elif balance < 3:
                problems.append(f"⚠️ Баланс OpenRouter низкий: ${balance:.2f}")
        except Exception as e:
            problems.append(f"⚠️ Не удалось проверить баланс OpenRouter ({e})")

    save_state(state)

    if problems:
        text = "⚠️ <b>Мониторинг Grandvest</b>\n📅 " + msk.strftime("%d.%m.%Y %H:%M МСК") + "\n\n" + "\n\n".join(problems)
        send_alert(text)
        print("Отправлено предупреждение:\n" + text)
    else:
        print("Проблем не обнаружено, всё в норме")


if __name__ == "__main__":
    main()
