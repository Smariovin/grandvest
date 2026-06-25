#!/usr/bin/env python3
"""
Mega patch: 
1. Dumps all n8n Code nodes
2. Patches generation node: doubles max_tokens + expands prompt
3. Forces node 9 to use grandvest-publisher.yml
"""
import sqlite3, json, subprocess, sys, os, re

DB = '/opt/n8n/n8n_data/database.sqlite'
GH_PAT = os.environ.get('GH_PAT', '')

if not GH_PAT:
    print("WARNING: GH_PAT env var not set! Node 9 patch will use placeholder.")

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")
rows = cur.fetchall()

dump_lines = []
changed_count = 0

NEW_PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь содержательные, развернутые посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА (строго соблюдай):\n\n"
    "EMOJI [ЦЕПЛЯЮЩИЙ ЗАГОЛОВОК - суть новости в 8-12 словах]\n\n"
    "[ВВОДНЫЙ АБЗАЦ - 3-4 предложения]\n"
    "Начинай разнообразно: 'По данным...', 'Аналитики фиксируют...', 'Эксперты рынка отмечают...', 'Согласно последним данным...'\n"
    "Раскрой суть события, цифры, факты.\n\n"
    "[КОНТЕКСТ И ДЕТАЛИ - 3-4 предложения]\n"
    "Объясни причины тенденции. Приведи конкретные цифры, районы, сегменты рынка. Исторический контекст если уместно.\n\n"
    "[ВЛИЯНИЕ НА РЫНОК - 2-3 предложения]\n"
    "Что это значит для арендаторов, собственников, инвесторов?\n\n"
    "Комментарий Грандвест: [2-3 предложения от лица агентства]\n\n"
    "Практический совет: [2 предложения - конкретный совет для арендатора или инвестора]\n\n"
    "За подбором объекта - @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ:\n"
    "- Объем: 900-1200 символов (содержательно и развернуто, не короче!)\n"
    "- Только факты и профессиональный анализ\n"
    "- Без воды и общих фраз\n"
    "- Конкретные цифры, районы, ставки аренды если есть\n"
    "- Стиль: экспертный, но доступный"
)

for wf_id, wf_name, nodes_raw in rows:
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue

    dump_lines.append(f"\n{'='*60}")
    dump_lines.append(f"WORKFLOW: {wf_name} ({wf_id})")

    changed = False
    for n in nodes:
        name = n.get('name', '')
        ntype = n.get('type', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))
        
        if code and len(code) > 50:
            dump_lines.append(f"  NODE: {name}")
            dump_lines.append(f"  TYPE: {ntype}")
            dump_lines.append(f"  CODE ({len(code)} chars):")
            for line in code.split('\n')[:30]:
                dump_lines.append("    " + line)
            if len(code.split('\n')) > 30:
                dump_lines.append(f"    ... [{len(code.split(chr(10)))-30} more lines]")
            dump_lines.append("")

        # PATCH A: Узел генерации поста
        has_ai = (
            ('openrouter' in code.lower() and 'model' in code) or
            ('max_tokens' in code and 'messages' in code)
        )
        
        if has_ai and code:
            print(f"\n>>> GENERATION NODE: {name} in {wf_name}")
            new_code = code

            # 1. Удваиваем max_tokens
            def double_mt(m):
                old = int(m.group(1))
                new = min(old * 2, 4096)
                print(f"  max_tokens: {old} -> {new}")
                return f'"max_tokens": {new}'
            new_code = re.sub(r'"max_tokens":\s*(\d+)', double_mt, new_code)

            # 2. Ищем и заменяем системный промпт
            # В n8n Code узлах промпт обычно в виде строки JS
            sys_patterns = [
                # "role": "system", "content": "...PROMPT..."
                (r'("role"\s*:\s*"system"\s*,\s*"content"\s*:\s*")(.*?)(")', 2),
                (r'("content"\s*:\s*")(.*?)("\s*,\s*"role"\s*:\s*"system")', 2),
                # 'role': 'system', 'content': '...PROMPT...'
                (r"(role\s*:\s*'system'\s*,\s*content\s*:\s*')(.*?)(')", 2),
                (r"(content\s*:\s*')(.*?)('\s*,\s*role\s*:\s*'system')", 2),
                # Template literal multiline
                (r'(role\s*:\s*"system"[^}]*?content\s*:\s*`)(.*?)(`)', 2),
            ]
            
            found = False
            for pattern, group_idx in sys_patterns:
                m = re.search(pattern, new_code, re.DOTALL)
                if m:
                    old = m.group(group_idx)
                    print(f"  Found prompt ({len(old)} chars): {old[:80]!r}...")
                    # Escape для подстановки
                    esc = NEW_PROMPT.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace("'", "\\'")
                    new_code = new_code[:m.start(group_idx)] + esc + new_code[m.end(group_idx):]
                    found = True
                    print(f"  Replaced! New code len: {len(new_code)}")
                    break
            
            if not found:
                print(f"  Pattern not found. Code snippet:")
                # Show lines with model/role keywords
                for i, line in enumerate(code.split('\n')):
                    if any(kw in line.lower() for kw in ['system', 'role', 'content', 'prompt', 'пиши', 'expert', 'ты']):
                        print(f"    L{i}: {line[:150]}")

            if new_code != code:
                if 'jsCode' in params:
                    n['parameters']['jsCode'] = new_code
                else:
                    n['parameters']['code'] = new_code
                changed = True

        # PATCH B: Узел 9 - принудительно grandvest-publisher.yml
        is_node9 = ('9.' in name and 'Telegram' in name) or ('Отправка' in name and 'Telegram' in name)
        if is_node9 and code and 'grandvest-publisher' not in code:
            print(f"\n>>> FIXING NODE 9: {name}")
            
            node9_code = (
                "// Отправка в Telegram через grandvest-publisher.yml\n"
                "const postText = $('8. Подготовка данных поста').first().json.tg_post;\n"
                "const imageUrl = $('HTTP Request \u2014 fal.ai').first().json.images?.[0]?.url || '';\n"
                "\n"
                "if (!postText || postText.length < 10) {\n"
                "  throw new Error('postText empty: ' + JSON.stringify(postText));\n"
                "}\n"
                "\n"
                "console.log('Post length:', postText.length, 'chars');\n"
                "console.log('Preview:', postText.substring(0, 200));\n"
                "\n"
                "const GH_PAT = '" + (GH_PAT if GH_PAT else 'REPLACE_WITH_PAT') + "';\n"
                "const body = { ref: 'main', inputs: { message: postText, image_url: imageUrl } };\n"
                "\n"
                "const response = await this.helpers.httpRequest({\n"
                "  method: 'POST',\n"
                "  url: 'https://api.github.com/repos/Smariovin/grandvest/actions/workflows/grandvest-publisher.yml/dispatches',\n"
                "  headers: {\n"
                "    'Authorization': 'token ' + GH_PAT,\n"
                "    'Content-Type': 'application/json',\n"
                "    'Accept': 'application/vnd.github+json'\n"
                "  },\n"
                "  body: JSON.stringify(body)\n"
                "});\n"
                "\n"
                "console.log('Dispatch sent! Status OK');\n"
                "return [{ json: { status: 'dispatched', textLen: postText.length, imageUrl } }];"
            )
            
            n['parameters']['jsCode'] = node9_code
            changed = True
            print(f"  Node 9 patched!")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes = ? WHERE id = ?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))
        changed_count += 1

conn.commit()
conn.close()

print(f"\n\n=== NODES DUMP ===")
for line in dump_lines:
    print(line)

print(f"\n=== SUMMARY ===")
print(f"Updated {changed_count} workflows")

if changed_count > 0:
    result = subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, text=True, timeout=30)
    print(f"n8n restart: {result.returncode}")
    print("n8n restarted!")
