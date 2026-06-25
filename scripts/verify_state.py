#!/usr/bin/env python3
import sqlite3, json, os, urllib.request, base64

DB = '/opt/n8n/n8n_data/database.sqlite'
TOKEN = os.environ.get('GH_PAT', '')

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity WHERE id IN ('F24jvKiXJIs4wRiZ', 'SIPnV2mqmgMqUkLb')")

output = {}
for wf_id, wf_name, nodes_raw in cur.fetchall():
    nodes = json.loads(nodes_raw)
    output[wf_id] = {'name': wf_name, 'nodes': []}
    for n in nodes:
        name = n.get('name', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        if code and len(code) > 30:
            output[wf_id]['nodes'].append({
                'name': name,
                'code_len': len(code),
                'code': code  # полный код
            })
conn.close()

# Сохраняем в файл и коммитим в GitHub
result_json = json.dumps(output, ensure_ascii=False, indent=2)
print("=== RESULT ===")
print(result_json[:8000])

# Коммитим в репозиторий
if TOKEN:
    encoded = base64.b64encode(result_json.encode('utf-8')).decode('ascii')
    
    # Получаем SHA существующего файла
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/Smariovin/grandvest/contents/debug/nodes_state.json',
            headers={'Authorization': f'token {TOKEN}'}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            existing_sha = json.loads(r.read().decode()).get('sha')
    except:
        existing_sha = None
    
    payload = {'message': 'debug: nodes state dump', 'content': encoded}
    if existing_sha:
        payload['sha'] = existing_sha
    
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req2 = urllib.request.Request(
        'https://api.github.com/repos/Smariovin/grandvest/contents/debug/nodes_state.json',
        data=data,
        headers={'Authorization': f'token {TOKEN}', 'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        with urllib.request.urlopen(req2, timeout=30) as r:
            print("\nSaved to GitHub: debug/nodes_state.json")
    except Exception as e:
        print(f"\nCould not save to GitHub: {e}")
