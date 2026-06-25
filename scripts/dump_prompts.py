#!/usr/bin/env python3
import sqlite3, json, subprocess, os

DB = '/opt/n8n/n8n_data/database.sqlite'
OUTPUT = '/tmp/prompts_dump.json'

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")

result = {}
for wf_id, wf_name, nodes_raw in cur.fetchall():
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue
    result[wf_id] = {"name": wf_name, "nodes": []}
    for n in nodes:
        name = n.get('name', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        body = params.get('body', '')
        url = params.get('url', '')
        
        # Включаем все Code узлы и HTTP Request узлы с промптами
        if code or ('openrouter' in str(url).lower()) or ('claude' in str(body).lower()) or ('gemini' in str(body).lower()):
            result[wf_id]["nodes"].append({
                "name": name,
                "type": n.get('type', ''),
                "code": code[:5000] if code else '',
                "url": url,
                "body": str(body)[:3000] if body else ''
            })

conn.close()

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"Saved {sum(len(v['nodes']) for v in result.values())} nodes to {OUTPUT}")
print("---DUMP---")
print(json.dumps(result, ensure_ascii=False, indent=2))
