#!/usr/bin/env python3
"""
Одноразовый скрипт: выводит ПОЛНЫЙ код указанных узлов n8n workflow,
сохраняет результат в файл и коммитит его обратно в репозиторий,
чтобы можно было прочитать через raw.githubusercontent.com без скриншотов.
"""
import os, sys, json, base64, urllib.request, urllib.error

N8N_URL = os.environ.get("N8N_URL", "http://85.239.61.157:5678")
API_KEY = os.environ.get("N8N_API_KEY", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "Smariovin/grandvest")

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

out = []

wf = fetch_workflow(RSS_WORKFLOW_ID)
nodes = wf.get("nodes", [])
out.append(f"Workflow: {wf.get('name')} | active={wf.get('active')} | всего узлов: {len(nodes)}")

for name in TARGET_NODES:
    node = node_by_name(nodes, name)
    out.append("\n" + "=" * 70)
    out.append(f"NODE: {name}")
    out.append("=" * 70)
    if node is None:
        out.append("НЕ НАЙДЕН")
        continue
    params = node.get("parameters", {})
    out.append(f"type: {node.get('type')}")
    if "jsCode" in params:
        out.append("--- jsCode ---")
        out.append(params["jsCode"])
    if "functionCode" in params:
        out.append("--- functionCode ---")
        out.append(params["functionCode"])
    if "url" in params:
        out.append(f"--- url ---\n{params['url']}")
    if "jsonBody" in params:
        out.append("--- jsonBody ---")
        out.append(params["jsonBody"])
    if "bodyParametersJson" in params:
        out.append("--- bodyParametersJson ---")
        out.append(params["bodyParametersJson"])
    if "conditions" in params:
        out.append("--- conditions ---")
        out.append(json.dumps(params["conditions"], ensure_ascii=False, indent=2))
    if "options" in params and params.get("options"):
        out.append("--- options ---")
        out.append(json.dumps(params["options"], ensure_ascii=False, indent=2))
    known = {"jsCode", "functionCode", "url", "jsonBody", "bodyParametersJson", "conditions", "options"}
    if not (set(params.keys()) & known):
        out.append("--- raw parameters ---")
        out.append(json.dumps(params, ensure_ascii=False, indent=2))

out.append("\n" + "=" * 70)
out.append("DONE")

result_text = "\n".join(out)
print(result_text)

# Коммитим результат обратно в репозиторий
if GH_TOKEN:
    path = "scripts/output/dump_result.txt"
    api_url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # проверяем, существует ли файл (нужен sha для обновления)
    sha = None
    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            existing = json.loads(r.read().decode("utf-8"))
            sha = existing.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"WARN: couldn't check existing file: {e.code}")

    body = {
        "message": "chore: update dump_result.txt",
        "content": base64.b64encode(result_text.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha

    req = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode("utf-8"))
            print(f"\nCOMMITTED: {resp.get('commit', {}).get('sha', 'unknown')}")
    except urllib.error.HTTPError as e:
        print(f"ERROR committing result: {e.code} {e.read().decode()[:500]}")
else:
    print("WARN: GH_TOKEN не задан, результат не закоммичен")
