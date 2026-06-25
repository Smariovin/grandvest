#!/usr/bin/env python3
import json, base64, urllib.request, os

token = os.environ.get('GH_PAT', '')
if not token:
    print("No GH_PAT, skipping commit")
    exit(0)

with open('/tmp/nodes_state.json', 'rb') as f:
    content = f.read()
encoded = base64.b64encode(content).decode('ascii')
print(f"File size: {len(content)} bytes")

sha = None
try:
    req = urllib.request.Request(
        'https://api.github.com/repos/Smariovin/grandvest/contents/debug/nodes_state.json',
        headers={'Authorization': f'token {token}'}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        sha = json.loads(r.read().decode()).get('sha')
    print(f"Existing file SHA: {sha}")
except:
    print("File does not exist yet, creating...")

payload = {'message': 'debug: nodes state dump', 'content': encoded}
if sha:
    payload['sha'] = sha
data = json.dumps(payload).encode('utf-8')
req2 = urllib.request.Request(
    'https://api.github.com/repos/Smariovin/grandvest/contents/debug/nodes_state.json',
    data=data,
    headers={'Authorization': f'token {token}', 'Content-Type': 'application/json'},
    method='PUT'
)
try:
    with urllib.request.urlopen(req2, timeout=30) as r:
        result = json.loads(r.read().decode())
        print(f"COMMITTED! SHA: {result.get('content', {}).get('sha', '?')[:12]}")
except Exception as e:
    print(f"Commit error: {e}")
