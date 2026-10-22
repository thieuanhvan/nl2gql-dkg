# chatgpt_sheet.py - step 9 (comparison with ChatGPT required by the course): 50 test questions of the random split
# (6 per type, 7 for types 1 and 2) in one prompt with the full Chinese schema and 8 fixed examples from train (one per
# type), i.e. the paper's ICL setting. Paste work/chatgpt_50questions/prompt_chatgpt.txt into ChatGPT and save the reply as
# work/chatgpt_50questions/answers_chatgpt.txt, then score with: python code/score.py --chatgpt work/chatgpt_50questions/answers_chatgpt.txt
# Usage: python code/chatgpt_sheet.py
import collections
import os

from common import work, read_jsonl, write_jsonl, rng_for
from schema import render_schema

rng = rng_for('chatgpt_50questions')
test, train = read_jsonl(work('data', 'test.jsonl')), read_jsonl(work('data', 'train.jsonl'))
by = collections.defaultdict(list)
for x in test:
    by[x['type']].append(x)
quota = {t: 6 for t in range(1, 9)}
quota[1] += 1
quota[2] += 1                                   # 8 * 6 + 2 = 50
pick = []
for t in range(1, 9):
    pick += rng.sample(by[t], min(quota[t], len(by[t])))
rng.shuffle(pick)
demos = [rng.choice([x for x in train if x['type'] == t]) for t in range(1, 9)]

head = (f"[Schema of Graph DB]:\n{render_schema(cn=True)}\n\n"
        "[Task Description]: You are a graph database expert. Please write the corresponding graph query language "
        "(Neo4j Cypher) based on the schema and natural language. Node properties are accessed as var.prop "
        "(e.g. d.cured_prob_pct). Answer every question with ONE line in the exact format `Qxx: <query>` and nothing "
        "else (no explanations, no markdown).\n\n[Demonstrations]:\n"
        + '\n'.join(f"[NL]: {d['nl']}\n[GQL]: {d['gql']}" for d in demos) + '\n\n[Questions]:\n')
qs = '\n'.join(f"Q{i + 1:02d}: {x['nl']}" for i, x in enumerate(pick))
open(work('chatgpt_50questions', 'prompt_chatgpt.txt'), 'w', encoding='utf-8').write(head + qs + '\n')
write_jsonl(work('chatgpt_50questions', 'questions_50.jsonl'),
            [dict(q=f'Q{i + 1:02d}', id=x['id'], type=x['type'], nl=x['nl']) for i, x in enumerate(pick)])
if not os.path.exists(work('chatgpt_50questions', 'answers_chatgpt.txt')):
    open(work('chatgpt_50questions', 'answers_chatgpt.txt'), 'w', encoding='utf-8').write('')
print('questions', len(pick), 'per type', dict(sorted(collections.Counter(x['type'] for x in pick).items())),
      'prompt characters', len(head + qs))
