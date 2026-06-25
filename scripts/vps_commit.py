#!/usr/bin/env python3
"""
Reads n8n nodes from SQLite and commits result directly to GitHub via API
Run on VPS with: GH_PAT=xxx python3 /tmp/vps_commit.py
"""
import sqlite3, json, base64, os, urllib.request, urllib.error

DB = '/opt/n8n/n8n_data/database.sqlite'
TOKEN = os.environ.get('GH_PAT', '')

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id IN ('F24jvKiXJIs4wRiZ', 'SIPnV2mqmgMqUkLb')")

output = {}
for wf_id, wf_name, nodes_raw in cur.fetchall():
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue
    output[wf_id] = {'name': wf_name, 'nodes': []}
    for n in nodes:
        name = n.get('name', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        if code and len(code) > 30:
            output[wf_id]['nodes'].append({
                'name': name,
                'code_len': len(code),
                'code': code
            })
conn.close()

result = json.dumps(output, ensure_ascii=False, indent=2)
print(f"Read {sum(len(v['nodes']) for v in output.values())} nodes, {len(result)} chars")
print("=== CONTENT ===")
print(result[:8000])

if not TOKEN:
    print("No GH_PAT, cannot commit")
    exit(0)

encoded = base64.b64encode(result.encode('utf-8')).decode('ascii')

sha = None
try:
    req = urllib.request.Request(
        'https://api.github.com/repos/Smariovin/grandvest/contents/debug/nodes_state.json',
        headers={'Authorization': f'token {TOKEN}'}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        sha = json.loads(r.read().decode()).get('sha')
    print(f"Existing SHA: {sha}")
except:
    print("New file")

payload = {'message': 'debug: n8n nodes state', 'content': encoded}
if sha: payload['sha'] = sha

data = json.dumps(payload).encode('utf-8')
req2 = urllib.request.Request(
    'https://api.github.com/repos/Smariovin/grandvest/contents/debug/nodes_state.json',
    data=data,
    headers={'Authorization': f'token {TOKEN}', 'Content-Type': 'application/json'},
    method='PUT'
)
try:
    with urllib.request.urlopen(req2, timeout=30) as r:
        result2 = json.loads(r.read().decode())
        print(f"COMMITTED! SHA: {result2.get('content',{}).get('sha','?')[:12]}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"Commit error {e.code}: {body[:300]}")
