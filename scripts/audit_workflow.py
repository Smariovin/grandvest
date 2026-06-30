#!/usr/bin/env python3
"""
Grandvest Workflow Auditor
Сверяет реально сохранённый/опубликованный код узлов n8n с ожидаемыми
фрагментами кода. Результат выводится только в консоль GitHub Actions.
"""
import os, sys, json, urllib.request, urllib.error

N8N_URL = os.environ.get("N8N_URL", "http://85.239.61.157:5678")
API_KEY = os.environ.get("N8N_API_KEY", "")

RSS_WORKFLOW_ID = "SIPnV2mqmqMqUkLb"
TG_WORKFLOW_ID = "F24jvKiXJIs4wRiZ"

if not API_KEY:
    print("ERROR: N8N_API_KEY не задан")
    sys.exit(1)

def fetch_workflow(workflow_id):
    url = f"{N8N_URL}/api/v1/workflows/{workflow_id}"
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"ERROR fetching {workflow_id}: {e.code} {e.read().decode()[:300]}")
        return None
    except Exception as e:
        print(f"ERROR fetching {workflow_id}: {e}")
        return None

def get_node_code(node):
    params = node.get("parameters", {})
    if "jsCode" in params:
        return params["jsCode"]
    if "functionCode" in params:
        return params["functionCode"]
    return json.dumps(params, ensure_ascii=False)

def node_by_name(nodes, name):
    for n in nodes:
        if n.get("name") == name:
            return n
    return None

CHECKS = {
    f"RSS workflow ({RSS_WORKFLOW_ID})": {
        "workflow_id": RSS_WORKFLOW_ID,
        "nodes": [
            ("HTTP Request7", [
                ("max_tokens установлен в 3000", "max_tokens: 3000"),
                ("Формат A прописан", "ФОРМАТ A"),
                ("Формат B прописан", "ФОРМАТ B"),
                ("Маркер NOPOST для пустых новостей", "NOPOST"),
            ]),
            ("Code in JavaScript2", [
                ("Чтение из generated.choices (фикс обёртки)", "generated?.choices"),
                ("Фильтр NOPOST", "NOPOST"),
            ]),
            ("HTTP Request8", [
                ("Используется JSON.stringify для безопасной вставки", "JSON.stringify"),
            ]),
            ("Получение полного текста", [
                ("Узел существует", ""),
            ]),
        ]
    },
    f"Telegram parser workflow ({TG_WORKFLOW_ID})": {
        "workflow_id": TG_WORKFLOW_ID,
        "nodes": []
    }
}

print("=" * 60)
print("АУДИТ N8N WORKFLOW")
print("=" * 60)

any_failed = False

for group_name, group in CHECKS.items():
    print(f"\n━━━ {group_name} ━━━")
    wf = fetch_workflow(group["workflow_id"])
    if wf is None:
        print("❌ Не удалось получить workflow из n8n API")
        any_failed = True
        continue

    nodes = wf.get("nodes", [])
    print(f"Всего узлов: {len(nodes)} | Активен: {wf.get('active')}")

    for node_name, checks in group["nodes"]:
        node = node_by_name(nodes, node_name)
        if node is None:
            print(f"⚠️  Узел «{node_name}» НЕ НАЙДЕН в workflow")
            any_failed = True
            continue

        code = get_node_code(node)

        if not checks or (len(checks) == 1 and checks[0][1] == ""):
            print(f"✅ Узел «{node_name}» существует")
            continue

        print(f"🔍 Узел «{node_name}»:")
        for desc, substring in checks:
            found = substring in code
            mark = "✅" if found else "❌"
            if not found:
                any_failed = True
            print(f"   {mark} {desc}")

# ─── Проверка tg_send.py ───
print(f"\n━━━ scripts/tg_send.py ━━━")
tg_send_path = "scripts/tg_send.py"
if os.path.exists(tg_send_path):
    with open(tg_send_path, "r", encoding="utf-8") as f:
        tg_code = f.read()

    tg_checks = [
        ("Лимит подписи к фото 1024 символа", "1024"),
        ("Фолбэк без фото на 4096 символов", "4096"),
        ("Логика 'если есть фото и текст короткий'", "len(text) <= 1024"),
    ]
    for desc, substring in tg_checks:
        found = substring in tg_code
        mark = "✅" if found else "❌"
        if not found:
            any_failed = True
        print(f"   {mark} {desc}")
else:
    print("⚠️  Файл scripts/tg_send.py не найден в репозитории")
    any_failed = True

print("\n" + "=" * 60)
if any_failed:
    print("❌ АУДИТ ЗАВЕРШЁН: найдены несоответствия (см. выше ❌/⚠️)")
    sys.exit(1)
else:
    print("✅ АУДИТ ЗАВЕРШЁН: все проверки пройдены")
