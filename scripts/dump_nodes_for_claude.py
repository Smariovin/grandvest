#!/usr/bin/env python3
"""
Одноразовый скрипт: выводит ПОЛНЫЙ код указанных узлов n8n workflow
в лог GitHub Actions, чтобы можно было скопировать его текстом, без скриншотов.
"""
import os, sys, json, urllib.request, urllib.error

N8N_URL = os.environ.get("N8N_URL", "http://85.239.61.157:5678")
API_KEY = os.environ.get("N8N_API_KEY", "")

RSS_WORKFLOW_ID = "SIPnV2mqmqMqUkLb"

TARGET_NODES = [
    "Code in JavaScript1",
    "Code in JavaScript4",
    "Code in JavaScript5",
    "HTTP Request6",
    "HTTP Request7",
    "HTTP Request8",
    "If",
]

if not API_KEY:
    print("ERROR: N8N_API_KEY не задан")
    sys.exit(1)

def fetch_workflow(workflow_id):
    url = f"{N8N_URL}/api/v1/workflows/{workflow_id}"
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": API_KEY})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def node_by_name(nodes, name):
    for n in nodes:
        if n.get("name") == name:
            return n
    return None

wf = fetch_workflow(RSS_WORKFLOW_ID)
nodes = wf.get("nodes", [])
print(f"Workflow: {wf.get('name')} | active={wf.get('active')} | всего узлов: {len(nodes)}")

for name in TARGET_NODES:
    node = node_by_name(nodes, name)
    print("\n" + "=" * 70)
    print(f"NODE: {name}")
    print("=" * 70)
    if node is None:
        print("НЕ НАЙДЕН")
        continue
    params = node.get("parameters", {})
    print(f"type: {node.get('type')}")
    if "jsCode" in params:
        print("--- jsCode ---")
        print(params["jsCode"])
    if "functionCode" in params:
        print("--- functionCode ---")
        print(params["functionCode"])
    if "url" in params:
        print(f"--- url ---\n{params['url']}")
    if "jsonBody" in params:
        print("--- jsonBody ---")
        print(params["jsonBody"])
    if "bodyParametersJson" in params:
        print("--- bodyParametersJson ---")
        print(params["bodyParametersJson"])
    if "conditions" in params:
        print("--- conditions ---")
        print(json.dumps(params["conditions"], ensure_ascii=False, indent=2))
    if "options" in params and params.get("options"):
        print("--- options ---")
        print(json.dumps(params["options"], ensure_ascii=False, indent=2))
    # Если ни одно из известных полей не нашлось — печатаем все параметры целиком
    known = {"jsCode", "functionCode", "url", "jsonBody", "bodyParametersJson", "conditions", "options"}
    if not (set(params.keys()) & known):
        print("--- raw parameters ---")
        print(json.dumps(params, ensure_ascii=False, indent=2))

print("\n" + "=" * 70)
print("DONE")
