#!/usr/bin/env python3
import os, sys, json, base64, traceback, urllib.request, urllib.error

N8N_URL = os.environ.get("N8N_URL", "http://85.239.61.157:5678")
API_KEY = os.environ.get("N8N_API_KEY", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "Smariovin/grandvest")

RSS_WORKFLOW_ID = "SIPnV2mqmqMqUkLb"
TARGET_NODES = [
    "Code in JavaScript1", "Code in JavaScript4", "Code in JavaScript5",
    "HTTP Request6", "HTTP Request7", "HTTP Request8", "If",
]

out = []
out.append(f"API_KEY set: {bool(API_KEY)} (len={len(API_KEY)})")
out.append(f"GH_TOKEN set: {bool(GH_TOKEN)} (len={len(GH_TOKEN)})")
out.append(f"REPO: {REPO}")

try:
    if not API_KEY:
        out.append("ERROR: N8N_API_KEY не задан в secrets")
    else:
        url = f"{N8N_URL}/api/v1/workflows/{RSS_WORKFLOW_ID}"
        req = urllib.request.Request(url, headers={"X-N8N-API-KEY": API_KEY})
        with urllib.request.urlopen(req, timeout=20) as r:
            wf = json.loads(r.read().decode("utf-8"))
        nodes = wf.get("nodes", [])
        out.append(f"Workflow: {wf.get('name')} | active={wf.get('active')} | всего узлов: {len(nodes)}")

        def node_by_name(nodes, name):
            for n in nodes:
                if n.get("name") == name:
                    return n
            return None

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
            for key in ["jsCode", "functionCode", "url", "jsonBody", "bodyParametersJson"]:
                if key in params:
                    out.append(f"--- {key} ---")
                    out.append(str(params[key]))
            if "conditions" in params:
                out.append("--- conditions ---")
                out.append(json.dumps(params["conditions"], ensure_ascii=False, indent=2))
            if params.get("options"):
                out.append("--- options ---")
                out.append(json.dumps(params["options"], ensure_ascii=False, indent=2))
            known = {"jsCode", "functionCode", "url", "jsonBody", "bodyParametersJson", "conditions", "options"}
            if not (set(params.keys()) & known):
                out.append("--- raw parameters ---")
                out.append(json.dumps(params, ensure_ascii=False, indent=2))

        out.append("\n" + "=" * 70)
        out.append("DONE FETCHING")
except Exception as e:
    out.append("EXCEPTION DURING FETCH:")
    out.append(traceback.format_exc())

result_text = "\n".join(out)
print(result_text)

# Коммитим результат обратно в репозиторий (всегда, даже если выше была ошибка)
try:
    if not GH_TOKEN:
        print("WARN: GH_TOKEN пуст, коммит результата невозможен")
    else:
        path = "scripts/output/dump_result.txt"
        api_url = f"https://api.github.com/repos/{REPO}/contents/{path}"
        headers = {
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "dump-script",
        }
        sha = None
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                existing = json.loads(r.read().decode("utf-8"))
                sha = existing.get("sha")
        except urllib.error.HTTPError as e:
            print(f"GET existing file status: {e.code}")

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
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode("utf-8"))
            print(f"\nCOMMITTED: {resp.get('commit', {}).get('sha', 'unknown')}")
except urllib.error.HTTPError as e:
    print(f"ERROR committing result: {e.code} {e.read().decode()[:1000]}")
except Exception as e:
    print("EXCEPTION DURING COMMIT:")
    print(traceback.format_exc())
