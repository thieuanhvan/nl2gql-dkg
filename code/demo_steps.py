# demo_steps.py - follow ONE test question back through every intermediate product of the pipeline, so the
# intermediate steps can be shown, not only the final score. Reads files only (no Neo4j, no GPU).
#   step 3b  ChatGPT reply line that proposed the template   work/gpt/responses/round<r>_type<t>.txt
#   step 3c  syntax/schema check of that pair                  work/gpt/candidates/round<r>.jsonl
#   step 3d-e CoT explanation, rewritten question, similarity  work/gpt/candidates/cot_round<r>.jsonl
#   step 3f  grounded pairs of the template (train and test)   work/data/{train,test}.jsonl
#   step 4   relevant schema given to the model                work/data_kaggle/test.jsonl
#   step 6   Cypher written by the model on Kaggle              work/out/random/preds/<job>.jsonl
#   step 7   EM and EX of the question                          work/scores/random/<job>_items.jsonl
# Usage (from the folder that contains code/ and work/):
#   python code/demo_steps.py                     test_0161, ft7_relcn
#   python code/demo_steps.py --id test_0108 --job ft7_full
import argparse
import json
import os
import re
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--id', default='test_0161')
ap.add_argument('--job', default='ft7_relcn')
a = ap.parse_args()
W = 'work'
LINE = '=' * 100


def rd(p):
    return [json.loads(x) for x in open(p, encoding='utf-8')] if os.path.exists(p) else []


def head(title):
    print(LINE)
    print(title)


test = {x['id']: x for x in rd(f'{W}/data_kaggle/test.jsonl')}
if a.id not in test:
    sys.exit(f'{a.id} not in {W}/data_kaggle/test.jsonl')
q = test[a.id]
tid = re.sub(r'_\d+$', '', q['tid'])                       # G1_5_00_1 -> template G1_5_00
m = re.match(r'G(\d+)_', tid)
rnd = int(m.group(1)) if m else 0

head(f'CÂU TEST {a.id}  loại {q["type"]} ({q["type_name"]})  template {tid}')
print('  Câu hỏi:', q['nl'])
print('  Cypher đúng:', q['gql'])

if rnd == 0:
    head('BƯỚC 3a  template hạt giống (nhóm viết tay, code/seeds_vi.jsonl)')
    print('  ', q['gql_template'])
else:
    head(f'BƯỚC 3b  ChatGPT đề xuất template (vòng {rnd}, work/gpt/responses/round{rnd}_type{q["type"]}.txt)')
    p = f'{W}/gpt/responses/round{rnd}_type{q["type"]}.txt'
    for line in open(p, encoding='utf-8'):
        if q['gql_template'] in line.replace('\\"', '"'):
            print('  ', line.strip())
            break
    cand = next((x for x in rd(f'{W}/gpt/candidates/round{rnd}.jsonl') if x['tid'] == tid), None)
    head(f'BƯỚC 3c  kiểm định dạng, tên schema, cú pháp Neo4j (work/gpt/candidates/round{rnd}.jsonl)')
    allc = rd(f'{W}/gpt/candidates/round{rnd}.jsonl')
    inpool = sum(1 for x in rd(f'{W}/gpt/pool.jsonl') if x.get('source') == 'chatgpt' and x.get('round') == rnd)
    print(f'  vòng {rnd}: ChatGPT đề xuất {len(allc)} cặp; vào kho (work/gpt/pool.jsonl) {inpool} template')
    print('  cặp này:', 'QUA' if cand and not cand['problems'] else f'LOẠI {cand["problems"] if cand else "?"}')
    cot = next((x for x in rd(f'{W}/gpt/candidates/cot_round{rnd}.jsonl') if x['tid'] == tid), None)
    if cot:
        head(f'BƯỚC 3d-3e  CoT: ChatGPT giải thích truy vấn rồi viết lại câu hỏi; giữ câu có độ giống >= 0.8')
        print('  Giải thích :', cot['cot'])
        print('  Viết lại   :', cot['rewritten'])
        for nl, s in zip(cot['nl'], cot['sims']):
            print(f'  {s:.4f}  {"giữ" if nl in cot["kept"] else "bỏ"}  {nl}')

head('BƯỚC 3f  grounding: điền tên thật từ Neo4j, chỉ giữ câu có kết quả (work/data/*.jsonl)')
for sp in ('train', 'dev', 'test'):
    rows = [x for x in rd(f'{W}/data/{sp}.jsonl') if re.sub(r'_\d+$', '', x['tid']) == tid]
    print(f'  {sp}: {len(rows)} câu cùng template', '' if not rows else f'(ví dụ: {rows[0]["nl"]})')
print('  -> câu test và câu train cùng template, chỉ khác tên thực thể')

head('BƯỚC 4  schema liên quan đưa vào prompt (label linker + A*, work/data_kaggle/test.jsonl)')
print('  nodes:', q['nodes'], '| edges:', [e[0] for e in q['edges']])
ctx = q['ctx_rel_cn']
k = ctx.find('Edges')                                        # the edge list is what decides the Cypher pattern
print('  ' + ctx[k if k >= 0 else 0:].strip().replace('\n', '\n  '))
print(f'  (cả đoạn schema trong prompt: {len(ctx)} ký tự)')

head(f'BƯỚC 6  Cypher mô hình {a.job} viết trên Kaggle (work/out/random/preds/{a.job}.jsonl)')
pred = next((x for x in rd(f'{W}/out/random/preds/{a.job}.jsonl') if x['id'] == a.id), {})
print('  ', pred.get('pred'))

head(f'BƯỚC 7  chấm trên Neo4j (work/scores/random/{a.job}_items.jsonl)')
it = next((x for x in rd(f'{W}/scores/random/{a.job}_items.jsonl') if x['id'] == a.id), {})
print(f'  EM = {it.get("em")}   EX = {it.get("ex")}   (chạy lại trực tiếp: python code/demo_emex.py --ids {a.id})')
print(LINE)
