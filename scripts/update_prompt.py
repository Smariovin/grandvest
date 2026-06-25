#!/usr/bin/env python3
"""
Update Claude/Gemini post generation prompt in n8n workflows
Doubles the post length - reads all nodes and shows current prompts
"""
import sqlite3, json, subprocess, sys, re

DB = '/opt/n8n/n8n_data/database.sqlite'

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")

all_nodes = []
updated_workflows = []

for wf_id, wf_name, nodes_raw in cur.fetchall():
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue
    
    changed = False
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        body = params.get('body', '')
        
        # Dump all nodes with meaningful code
        if code and len(code) > 100:
            all_nodes.append({
                'wf': wf_name,
                'wf_id': wf_id,
                'node': name,
                'type': ntype,
                'code_len': len(code),
                'code_preview': code[:300],
                'has_openrouter': 'openrouter' in code.lower(),
                'has_claude': 'claude' in code.lower(),
                'has_gemini': 'gemini' in code.lower(),
                'has_max_tokens': 'max_tokens' in code,
                'has_messages': 'messages' in code,
            })
        
        if body and len(str(body)) > 100:
            all_nodes.append({
                'wf': wf_name,
                'wf_id': wf_id,
                'node': name + ' [BODY]',
                'type': ntype,
                'code_len': len(str(body)),
                'code_preview': str(body)[:300],
                'has_openrouter': 'openrouter' in str(body).lower(),
                'has_claude': 'claude' in str(body).lower(),
                'has_gemini': 'gemini' in str(body).lower(),
                'has_max_tokens': 'max_tokens' in str(body),
                'has_messages': 'messages' in str(body),
            })

conn.close()

print("=== ALL NODES WITH CODE ===")
for info in all_nodes:
    flags = []
    if info['has_openrouter']: flags.append('OPENROUTER')
    if info['has_claude']: flags.append('CLAUDE')
    if info['has_gemini']: flags.append('GEMINI')
    if info['has_max_tokens']: flags.append('MAX_TOKENS')
    if info['has_messages']: flags.append('MESSAGES')
    
    print(f"\n{'='*50}")
    print(f"WF: {info['wf']} ({info['wf_id']})")
    print(f"NODE: {info['node']}")
    print(f"TYPE: {info['type']}")
    print(f"FLAGS: {', '.join(flags) if flags else 'none'}")
    print(f"CODE ({info['code_len']} chars):")
    print(info['code_preview'])
    if info['code_len'] > 300:
        print(f"... [truncated, {info['code_len'] - 300} more chars]")

print("\n=== DONE ===")
