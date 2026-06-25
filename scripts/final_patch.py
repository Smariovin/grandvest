#!/usr/bin/env python3
# Финальный патч: полностью заменяет код узла генерации поста
import sqlite3, json, subprocess, sys, os

DB = '/opt/n8n/n8n_data/database.sqlite'
OR_KEY = os.environ.get('OPENROUTER_KEY', '')

if not OR_KEY:
    # Читаем из существующего кода в БД
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT nodes FROM workflow_entity WHERE id='F24jvKiXJIs4wRiZ'")
    row = cur.fetchone()
    conn.close()
    if row:
        import re
        keys = re.findall(r'sk-or-v1-[a-f0-9]+', row[0])
        if keys:
            OR_KEY = keys[0]
            print(f"Found OR key in DB: {OR_KEY[:20]}...")

SYSTEM_PROMPT = (
    "Ты - эксперт по коммерческой недвижимости Москвы с 15-летним опытом. "
    "Пишешь содержательные, аналитические посты для Telegram канала агентства Grandvest.\n\n"
    "СТРУКТУРА ПОСТА (строго соблюдай):\n\n"
    "EMOJI [ЗАГОЛОВОК - конкретная суть новости, 8-12 слов]\n\n"
    "АБЗАЦ 1 - ФАКТЫ (3-4 предложения): начинай разнообразно: "
    "'По данным...', 'Аналитики фиксируют...', 'Эксперты рынка отмечают...', "
    "'Согласно последним данным...'. Конкретные факты с цифрами.\n\n"
    "АБЗАЦ 2 - КОНТЕКСТ (3-4 предложения): почему происходит? "
    "Районы, сегменты, ставки аренды. Сравнение с предыдущим периодом.\n\n"
    "АБЗАЦ 3 - ВЛИЯНИЕ НА РЫНОК (2-3 предложения): "
    "что это значит для арендаторов, инвесторов, собственников?\n\n"
    "EMOJI Комментарий Грандвест: 2-3 предложения от лица агентства.\n\n"
    "EMOJI Практический совет: 2 конкретных предложения.\n\n"
    "За подбором объекта - @Grandvest_bot\n\n"
    "#коммерческаянедвижимость #аренда #москва #грандвест\n\n"
    "ТРЕБОВАНИЯ: длина 900-1200 символов. Только конкретика. Никакой воды."
)

NEW_CODE_TEMPLATE = '''// Генерация поста через OpenRouter (Claude)
const inputText = $input.first().json.text || $input.first().json.content || $input.first().json.message || '';

if (!inputText || inputText.length < 20) {{
  throw new Error('Нет текста: ' + JSON.stringify($input.first().json).substring(0, 200));
}}

const systemPrompt = `{system}`;

const response = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://openrouter.ai/api/v1/chat/completions',
  headers: {{
    'Authorization': 'Bearer {key}',
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://grandvest.ru',
    'X-Title': 'Grandvest'
  }},
  body: JSON.stringify({{
    model: 'anthropic/claude-sonnet-4-5',
    max_tokens: 2048,
    messages: [
      {{ role: 'system', content: systemPrompt }},
      {{ role: 'user', content: `Напиши экспертный пост о коммерческой недвижимости по новости:\\n\\n${{inputText}}` }}
    ]
  }})
}});

const postText = response.choices?.[0]?.message?.content || '';
console.log('Post length:', postText.length, 'chars');
console.log('Preview:', postText.substring(0, 200));

return [{{ json: {{ ...($input.first().json), generated_post: postText, post_length: postText.length }} }}];'''

NEW_CODE_RSS_TEMPLATE = '''// Генерация поста через OpenRouter (Gemini для RSS)
const inputText = $input.first().json.title || $input.first().json.text || '';

if (!inputText || inputText.length < 10) {{
  throw new Error('No input: ' + JSON.stringify($input.first().json).substring(0, 100));
}}

const systemPrompt = `{system}`;

const response = await this.helpers.httpRequest({{
  method: 'POST',
  url: 'https://openrouter.ai/api/v1/chat/completions',
  headers: {{
    'Authorization': 'Bearer {key}',
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://grandvest.ru',
    'X-Title': 'Grandvest'
  }},
  body: JSON.stringify({{
    model: 'google/gemini-flash-1.5',
    max_tokens: 2048,
    messages: [
      {{ role: 'system', content: systemPrompt }},
      {{ role: 'user', content: `Напиши экспертный пост о недвижимости по новости:\\n\\n${{inputText}}` }}
    ]
  }})
}});

const postText = response.choices?.[0]?.message?.content || '';
console.log('Post length:', postText.length);
return [{{ json: {{ ...($input.first().json), generated_post: postText }} }}];'''

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, name, nodes FROM workflow_entity")

patched = []
all_found = []

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
        if not code:
            continue

        has_or = 'openrouter' in code.lower()
        has_mt = 'max_tokens' in code
        has_msg = 'messages' in code

        if has_or or has_mt:
            all_found.append(f"  WF={wf_name!r:35} NODE={name!r:40} OR={has_or} MT={has_mt} MSG={has_msg} LEN={len(code)}")

        if (has_or and has_msg) or (has_mt and has_msg and 'openrouter' in code.lower()):
            print(f"\nFOUND: {name!r} in {wf_name!r} ({len(code)} chars)")
            print(f"First 300 chars:\n{code[:300]}")
            
            # Извлекаем ключ из существующего кода если не передан
            key = OR_KEY
            if not key:
                import re
                keys = re.findall(r'sk-or-v1-[a-f0-9]+', code)
                if keys:
                    key = keys[0]
                    print(f"  Extracted key: {key[:20]}...")

            if not key:
                print(f"  ERROR: No OpenRouter key found!")
                continue

            sys_esc = SYSTEM_PROMPT.replace('`', '\\`').replace('${', '\\${')

            if wf_id == 'F24jvKiXJIs4wRiZ':
                new_code = NEW_CODE_TEMPLATE.format(system=sys_esc, key=key)
            else:
                new_code = NEW_CODE_RSS_TEMPLATE.format(system=sys_esc, key=key)

            n['parameters']['jsCode'] = new_code
            if 'code' in params and 'jsCode' not in params:
                del n['parameters']['code']
                n['parameters']['jsCode'] = new_code
            changed = True
            patched.append(f"{wf_name} -> {name}")
            print(f"  PATCHED! New code: {len(new_code)} chars")

    if changed:
        cur.execute("UPDATE workflow_entity SET nodes = ? WHERE id = ?",
                    (json.dumps(nodes, ensure_ascii=False), wf_id))

conn.commit()
conn.close()

print("\n=== ALL OPENROUTER/AI NODES ===")
for info in all_found:
    print(info)

print(f"\n=== RESULT: PATCHED {len(patched)} nodes ===")
for p in patched:
    print(f"  {p}")

if patched:
    subprocess.run(['docker', 'restart', 'n8n'], capture_output=True, timeout=30)
    print("n8n restarted!")
else:
    print("\nWARNING: Nothing patched!")
    conn3 = sqlite3.connect(DB)
    cur3 = conn3.cursor()
    cur3.execute("SELECT id, name FROM workflow_entity")
    print("Workflows in DB:")
    for wid, wname in cur3.fetchall():
        print(f"  {wid!r}: {wname!r}")
    conn3.close()
