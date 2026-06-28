#!/usr/bin/env python3
"""RSS Workflow full diagnostic + fix - no hardcoded secrets"""
import sqlite3, json, urllib.request, urllib.parse, os, subprocess, time

DB = '/opt/n8n/n8n_data/database.sqlite'
BOT = os.environ.get('TG_BOT','')
CHAT = os.environ.get('TG_CHAT','5340000158')
OR_KEY = os.environ.get('OR_KEY','')

def tg(msg):
    if not BOT: print("TG:", msg[:300]); return
    url = 'https://api.telegram.org/bot' + BOT + '/sendMessage'
    data = urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4096],'parse_mode':'HTML'}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url,data=data,method='POST'),timeout=15)
    except Exception as e: print('TG err:', e)

print("=== RSS WORKFLOW DIAGNOSTIC ===")

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, active, nodes FROM workflow_entity")
all_wf = cur.fetchall()

rss_wf = None
for wf_id, wf_name, active, nodes_raw in all_wf:
    if 'RSS' in wf_name or 'Сбор новостей' in wf_name or 'rss' in wf_name.lower():
        rss_wf = (wf_id, wf_name, active, nodes_raw)
        print("Found RSS: [" + str(wf_id) + "] " + wf_name + " active=" + str(active))
        break

if not rss_wf:
    print("RSS not found! Workflows:")
    for wf_id, wf_name, active, _ in all_wf:
        print("  [" + str(wf_id) + "] " + wf_name + " active=" + str(active))
    tg("ERROR: RSS workflow not found!")
    conn.close()
    exit(0)

wf_id, wf_name, active, nodes_raw = rss_wf
nodes = json.loads(nodes_raw)
print("Nodes: " + str(len(nodes)))

node_report = []
for n in nodes:
    name = n.get('name','')
    ntype = n.get('type','')
    params = n.get('parameters',{})
    short_type = ntype.split('.')[-1]
    
    if ntype == 'n8n-nodes-base.scheduleTrigger':
        rule = str(params.get('rule',{}))[:60]
        print("Trigger: " + rule)
        node_report.append("TRIGGER|" + rule)
    
    elif ntype == 'n8n-nodes-base.httpRequest':
        url_v = params.get('url','')
        bct = params.get('bodyContentType','?')
        spec = params.get('specifyBody','?')
        method = params.get('method','GET')
        jb = str(params.get('jsonBody',''))
        rb = str(params.get('rawBody',params.get('body','')))
        print("HTTP [" + name + "] " + method + " " + url_v[:60])
        print("  bct=" + str(bct) + " spec=" + str(spec))
        if jb and jb != '': print("  jsonBody=" + jb[:200])
        if rb and rb != '': print("  rawBody=" + rb[:200])
        node_report.append("HTTP|" + name[:25] + "|bct=" + str(bct) + "|" + url_v[:40])
    
    elif ntype == 'n8n-nodes-base.code':
        code = params.get('jsCode','')
        print("Code [" + name + "] " + str(len(code)) + " chars")
        print(code[:300])
        node_report.append("Code|" + name[:25] + "|" + code[:60])
    
    elif ntype == 'n8n-nodes-base.merge':
        num = params.get('numberInputs','?')
        node_report.append("Merge|inputs=" + str(num))
        print("Merge inputs=" + str(num))
    
    elif ntype == 'n8n-nodes-base.if':
        conds = str(params.get('conditions',{}))[:80]
        node_report.append("If|" + conds)
        print("If " + conds)
    
    else:
        node_report.append(short_type + "|" + name[:25])

conn.close()

nr_str = "\n".join(node_report)
tg(
    "<b>RSS DIAGNOSTIC</b>\n"
    "ID: " + str(wf_id) + " | Active: " + str(active) + "\n"
    "Nodes: " + str(len(nodes)) + "\n\n"
    "<b>Список узлов:</b>\n" + nr_str[:2500]
)
print("DONE")
