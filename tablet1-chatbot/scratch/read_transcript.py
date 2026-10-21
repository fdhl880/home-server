import json

path = r'C:\Users\Asus\.gemini\antigravity-ide\brain\75bd94c0-e104-4f35-84ee-f785c2bfee19\.system_generated\logs\transcript.jsonl'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        obj = json.loads(line)
        si = obj.get('step_index')
        if si and 5820 <= si <= 5860:
            typ = obj.get('type')
            content = str(obj.get('content'))
            print(f"Step {si} [{typ}]: {content[:300]}")
