#!/usr/bin/env python3
# Читаем все узлы workflow F24jvKiXJIs4wRiZ и показываем их состояние
import sqlite3, json

DB = '/opt/n8n/n8n_data/database.sqlite'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
row = cur.fetchone()
conn.close()

if not row:
    print("Workflow not found!")
    exit(1)

nodes = json.loads(row[0])
print(f"Total nodes: {len(nodes)}\n")

for n in nodes:
    name = n.get('name', '')
    ntype = n.get('type', '')
    params = n.get('parameters', {})
    code = params.get('jsCode', params.get('code', ''))
    
    print(f"NODE: {name!r}")
    print(f"  TYPE: {ntype}")
    if code:
        print(f"  CODE ({len(code)} chars):")
        for line in code.split('\n')[:5]:
            print(f"    {line}")
        if len(code.split('\n')) > 5:
            print(f"    ... [{len(code.split(chr(10)))-5} more lines]")
    print()
