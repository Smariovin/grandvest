#!/usr/bin/env python3
# Patch n8n generation node: double max_tokens + expand system prompt
import sqlite3, json, subprocess, re

DB = '/opt/n8n/n8n_data/database.sqlite'

NEW_SYSTEM = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь содержательные, аналитические посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА (строго соблюдай):\n\n"
    "EMOJI [ЗАГОЛОВОК - конкретная суть новости, 8-12 слов]\n\n"
    "АБЗАЦ 1 - ФАКТЫ (3-4 предложения): начинай разнообразно: "
    "'По данным...', 'Аналитики фиксируют...', 'Эксперты рынка отмечают...', "
    "'Согласно последним данным...'. Излагай конкретные факты с цифрами.\n\n"
    "АБЗАЦ 2 - КОНТЕКСТ (3-4 предложения): почему это происходит? "
    "Назови конкретные районы, сегменты, ставки аренды. Сравни с предыдущим периодом.\n\n"
    "АБЗАЦ 3 - ВЛИЯНИЕ НА РЫНОК (2-3 предложения): что это значит для арендаторов, "
    "инвесторов, собственников? Какие сегменты выигрывают или проигрывают?\n\n"
    "EMOJI Комментарий Грандвест: 2-3 предложения от первого лица агентства. "
    "Профессиональная оценка, что это значит для клиентов.\n\n"
    "EMOJI Практический совет: 2 предложения. "
    "Конкретный actionable совет для арендатора или инвестора.\n\n"
    "За подбором объекта - @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ЖЁСТКИЕ ТРЕБОВАНИЯ:\n"
    "- Длина: 900-1200 символов. Если короче - дополни деталями.\n"
    "- Только конкретика: цифры, районы, ставки, сроки\n"
    "- Запрещена вода и общие фразы\n"
    "- Стиль: экспертный и деловой, понятный обычному человеку\n"
    "- Эмодзи только в начале заголовка и блоков"
)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")

patched = []
all_nodes = []

for wf_id, wf_name, nodes_raw in cur.fetchall():
    try:
        nodes = json.loads(nodes_raw)
    except:
        continue

    changed = False
    for n in nodes:
        name = n.get('name', '')
        params = n.get('parameters', {})
        code = params.get('jsCode', params.get('code', ''))

        if code and len(code) > 100:
            has_or = 'openrouter' in code.lower()
            has_mt = 'max_tokens' in code
            has_msg = 'messages' in code
            all_nodes.append(f"  WF={wf_name!r:30} NODE={name!r:35} LEN={len(code):5} OR={has_or} MT={has_mt} MSG={has_msg}")

            if has_or and has_mt and has_msg:
                print(f"\n{'='*60}")
                print(f"GENERATION NODE: {name!r} in {wf_name!r}")
                print(f"FULL CODE ({len(code)} chars):")
                print(code)
                print(f"{'='*60}")

                new_code = code

                # 1. Double max_tokens
                def dbl(m):
                    v = int(m.group(1))
                    nv = min(v * 2, 4096)
                    print(f"  max_tokens: {v} -> {nv}")
                    return '"max_tokens": ' + str(nv)
                new_code = re.sub(r'"max_tokens":\s*(\d+)', dbl, new_code)

                # 2. Find and replace system prompt
                patterns = [
                    (r'("role"\s*:\s*"system"\s*,\s*"content"\s*:\s*")((?:[^"\\]|\\.)*?)(")', 2),
                    (r'("content"\s*:\s*")((?:[^"\\]|\\.)*?)("\s*,\s*"role"\s*:\s*"system")', 2),
                    (r"('role'\s*:\s*'system'\s*,\s*'content'\s*:\s*')((?:[^'\\]|\\.)*?)(')", 2),
                    (r"('content'\s*:\s*')((?:[^'\\]|\\.)*?)('\s*,\s*'role'\s*:\s*'system')", 2),
                    (r'(role\s*:\s*["\']system["\']\s*,\s*content\s*:\s*")((?:[^"\\]|\\.)*?)(")', 2),
                    (r"(role\s*:\s*['\"]system['\"]\s*,\s*content\s*:\s*')((?:[^'\\]|\\.)*?)(')", 2),
                ]

                replaced = False
                for pat, grp in patterns:
                    m = re.search(pat, new_code, re.DOTALL)
                    if m and len(m.group(grp)) > 20:
                        old = m.group(grp)
                        print(f"  Found system prompt ({len(old)} chars): {old[:100]!r}...")
                        esc = NEW_SYSTEM.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace("'", "\\'")
                        new_code = new_code[:m.start(grp)] + esc + new_code[m.end(grp):]
                        replaced = True
                        print(f"  Replaced! New code: {len(new_code)} chars")
                        break

                if not replaced:
                    print("  WARNING: system prompt pattern not found!")
                    print("  Lines with keywords:")
                    for i, line in enumerate(code.split('\n'), 1):
                        if any(kw in line.lower() for kw in ['system', 'role', 'content', 'ты ', 'пиши', 'эксперт', 'структур', 'prompt']):
                            print(f"    L{i}: {line[:200]}")

                if new_code != code:
                    if 'jsCode' in params:
                        n['parameters']['jsCode'] = new_code
                    else:
                        n['parameters']['code'] = new_code
                    changed = True
                    patched.append(f"{wf_name} -> {name}")
                    print(f"  PATCHED!")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes = ? WHERE id = ?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

print("\n=== ALL CODE NODES ===")
for info in all_nodes:
    print(info)

print(f"\n=== RESULT ===")
if patched:
    for p in patched:
        print(f"  PATCHED: {p}")
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=30)
    print("n8n restarted!")
else:
    print("Nothing patched")
