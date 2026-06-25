#!/usr/bin/env python3
import sqlite3, json

DB = '/opt/n8n/n8n_data/database.sqlite'

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
                'code': code
            })
conn.close()

print(json.dumps(output, ensure_ascii=False, indent=2))
