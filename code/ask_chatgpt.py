# ask_chatgpt.py - ask ChatGPT (OpenAI API, code/gpt_api.py) the same new questions, with the prompt of step 9
# (full schema with explanations + the 8 fixed demonstrations of work/chatgpt_50questions/prompt_chatgpt.txt), 50 questions
# per call. Answers are merged into one file of lines "<id>: <Cypher>" for code/score_ask.py.
# Usage (from the folder that contains code/ and work/):
#   python code/ask_chatgpt.py                       questions of demo/diabetes_all_gold.jsonl
#   python code/ask_chatgpt.py <gold.jsonl> <out.txt>
import json
import os
import re
import subprocess
import sys

gold = sys.argv[1] if len(sys.argv) > 1 else 'demo/diabetes_all_gold.jsonl'
out = sys.argv[2] if len(sys.argv) > 2 else 'demo/diabetes_all_chatgpt.txt'
qs = [json.loads(x) for x in open(gold, encoding='utf-8')]
base = open('work/chatgpt_50questions/prompt_chatgpt.txt', encoding='utf-8').read()
head = base[:base.index('[Questions]:')]
head = head.replace('`Qxx: <query>`', '`<id>: <query>` (the id given before each question, e.g. D001)')
tmp = 'work/chatgpt_parts'                                 # prompts and raw answers of each call
os.makedirs(tmp, exist_ok=True)
answers = {}
for k in range(0, len(qs), 50):
    part = qs[k:k + 50]
    name = f'part{k // 50 + 1:02d}'
    open(f'{tmp}/{name}_prompt.txt', 'w', encoding='utf-8').write(
        head + '[Questions]:\n' + '\n'.join(f"{q['id']}: {q['nl']}" for q in part) + '\n')
    subprocess.run([sys.executable, 'code/gpt_api.py', '--prompt-file', f'{tmp}/{name}_prompt.txt',
                    '--out-file', f'{tmp}/{name}_answers.txt'], check=True)
    text = open(f'{tmp}/{name}_answers.txt', encoding='utf-8').read().replace('```cypher', '').replace('```', '')
    for line in text.splitlines():
        m = re.match(r'\s*\**\s*([A-Z]\d+)\s*\**\s*:\s*(.+)', line)
        if m:
            answers[m.group(1)] = m.group(2).strip()
with open(out, 'w', encoding='utf-8') as f:
    for q in qs:
        f.write(f"{q['id']}: {answers.get(q['id'], '')}\n")
print(f'{len(answers)}/{len(qs)} answers ->', out)
