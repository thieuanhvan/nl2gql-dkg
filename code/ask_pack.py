# ask_pack.py - prepare the Kaggle kernel that asks the fine-tuned model new questions (code/ask_kaggle.py).
# For each question the relevant schema is extracted exactly as for the test set (label linker + trigger words + A*,
# metrics.py); the entity dictionary is read from data/names_vi.tsv, so no Neo4j is needed (it gives the same contexts
# as build_contexts.py for the test questions). Default questions: the 8 Đái tháo đường (diabetes) questions of the demo.
# Usage (from the folder that contains code/, data/ and work/):
#   python code/ask_pack.py [questions.txt|gold.jsonl]  one question per line, or a .jsonl with id and nl;
#                                                  default: the 8 diabetes questions
#   kaggle kernels push -p work/kaggle/nl2gql-dkg-ask --accelerator NvidiaTeslaT4
#   kaggle kernels output <user>/nl2gql-dkg-ask -p work/out/ask
import collections
import json
import os
import sys

sys.path.insert(0, 'code')
os.environ.setdefault('NL2GQL_LANG', 'vi')
from metrics import SchemaExtractor, render_items  # noqa: E402

USER = os.environ.get('KAGGLE_USER', 'vanthieu')
DIR = 'work/kaggle/nl2gql-dkg-ask'
DEFAULT = ['Đái tháo đường cần làm những xét nghiệm nào?',
           'Người bị Đái tháo đường thường dùng thuốc gì?',
           'Bị Đái tháo đường thì nên kiêng ăn gì?',
           'Chi phí điều trị cao nhất của Đái tháo đường là bao nhiêu tệ?',
           'Triệu chứng xếp đầu trong danh sách triệu chứng của Đái tháo đường là gì?',
           'Đái tháo đường có biến chứng Tăng huyết áp không?',
           'Bệnh nào thường dùng Viên nén metformin hydroclorid và có triệu chứng Uống nhiều?',
           'Bệnh tiểu đường cần làm những xét nghiệm nào?']
qs = [(f'Q{i:02d}', q) for i, q in enumerate(DEFAULT, 1)]
if len(sys.argv) > 1:
    src = sys.argv[1]
    if src.endswith('.jsonl'):                               # e.g. demo/diabetes_all_gold.jsonl (id, nl, gql, ...)
        qs = [(r['id'], r['nl']) for r in (json.loads(x) for x in open(src, encoding='utf-8'))]
    else:
        qs = [(f'Q{i:02d}', x.strip()) for i, x in enumerate((y for y in open(src, encoding='utf-8') if y.strip()), 1)]

n2l = collections.defaultdict(set)
for line in open('data/names_vi.tsv', encoding='utf-8'):
    p = line.rstrip('\n').split('\t')
    if not line.startswith('#') and len(p) == 3 and len(p[2]) >= 2:
        n2l[p[2]].add(p[0])
train = [json.loads(x) for x in open('work/data/train.jsonl', encoding='utf-8')]
ex = SchemaExtractor(n2l, train)

rows = []
for qid, nl in qs:
    labels, edges = ex.extract(nl)
    rows.append(dict(id=qid, nl=nl, nodes=sorted(labels), edges=[list(e) for e in sorted(edges)],
                     ctx_rel_cn=render_items(labels, edges, cn=True)))
    if len(qs) <= 20:
        print(qid, nl, '| nodes', sorted(labels), '| edges', [e[0] for e in sorted(edges)])

os.makedirs(DIR, exist_ok=True)
src = open('code/ask_kaggle.py', encoding='utf-8').read()
open(f'{DIR}/ask_kaggle.py', 'w', encoding='utf-8').write(src.replace('__QUESTIONS__', json.dumps(rows, ensure_ascii=False)))
with open(f'{DIR}/questions.jsonl', 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
json.dump(dict(id=f'{USER}/nl2gql-dkg-ask', title='nl2gql-dkg-ask', code_file='ask_kaggle.py', language='python',
               kernel_type='script', is_private=True, enable_gpu=True, enable_internet=True, dataset_sources=[],
               competition_sources=[], kernel_sources=[f'{USER}/nl2gql-dkg']),
          open(f'{DIR}/kernel-metadata.json', 'w', encoding='utf-8'), indent=1)
print('written', DIR, '(', len(rows), 'questions )')
