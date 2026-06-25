#!/usr/bin/env python3
import sqlite3, json, sys

DB = '/opt/n8n/n8n_data/database.sqlite'
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Ищем в обоих workflow
cur.execute("SELECT id, name, nodes FROM workflow_entity")
for wf_id, wf_name, nodes_raw in cur.fetchall():
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        
        # Ищем узел с промптом для генерации поста
        if ('генерац' in name.lower() or 'пост' in name.lower() or 
            'openrouter' in code.lower() or 'claude' in code.lower() or
            'gemini' in code.lower() or 'httpRequest' in name.lower()):
            print(f"\n{'='*60}")
            print(f"WORKFLOW: {wf_name} (ID: {wf_id})")
            print(f"NODE: {name}")
            print(f"TYPE: {ntype}")
            if code:
                print(f"CODE ({len(code)} chars):")
                print(code)
            # Также смотрим url и body для HTTP Request узлов
            if 'url' in params:
                print(f"URL: {params['url']}")
            if 'body' in params:
                body = params.get('body', '')
                print(f"BODY ({len(str(body))} chars): {str(body)[:2000]}")

conn.close()
