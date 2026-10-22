# score_ask.py - EM and EX of answers "<id>: <Cypher>" against a gold file (demo/diabetes_all_gold.jsonl by default),
# with totals per part (A: from templates, H: written by hand, S: everyday name "tiểu đường") and per question type.
# Usage (from the folder that contains code/ and work/; needs the Neo4j password for EX):
#   python code/score_ask.py work/out/ask/answers_ft7_relcn.txt
#   python code/score_ask.py demo/diabetes_all_chatgpt.txt
#   python code/score_ask.py <answers> --gold demo/diabetes_all_gold.jsonl --show-wrong
# Output: work/scores/ask/<answers name>_<YYYYMMDD_HHMM>.json (totals, per part, per type, every question).
import argparse
import collections
import getpass
import json
import os
import re
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument('answers')
ap.add_argument('--gold', default='demo/diabetes_all_gold.jsonl')
ap.add_argument('--show-wrong', action='store_true', help='print every question with EM 0 or EX 0')
a = ap.parse_args()
os.environ.setdefault('NL2GQL_LANG', 'vi')
if not os.environ.get('NEO4J_PASSWORD'):
    os.environ['NEO4J_PASSWORD'] = getpass.getpass('Neo4j DBMS password (not echoed): ')
sys.path.insert(0, 'code')
from common import run  # noqa: E402
from metrics import exact_match, exec_match, gold_rows  # noqa: E402

gold = [json.loads(x) for x in open(a.gold, encoding='utf-8')]
text = open(a.answers, encoding='utf-8').read().replace('```cypher', '').replace('```', '')
ans = {}
for line in text.splitlines():
    m = re.match(r'\s*\**\s*([A-Z]\d+)\s*\**\s*:\s*(.+)', line)
    if m:
        ans[m.group(1)] = m.group(2).strip()
try:                                                          # wrong password or Neo4j not started: say so plainly
    run('RETURN 1')
except Exception as e:
    sys.exit(f'DỪNG: không nối được Neo4j ({str(e).splitlines()[0][:120]}). Kiểm Neo4j Desktop đã Start, '
             'CSDL diseasekg-vi, và gõ đúng mật khẩu.')
if not gold_rows(gold[0]['gql']):                             # every gold query returned rows when it was built
    sys.exit(f"DỪNG: câu đúng {gold[0]['id']} ra 0 dòng. Kiểm CSDL đang nối (NEO4J_DB={os.environ.get('NEO4J_DB', 'mặc định')}), "
             "phải là diseasekg-vi và Neo4j đã Start.")
t0 = time.time()
items = []
for g in gold:
    p = ans.get(g['id'], '')
    items.append(dict(id=g['id'], part=g['part'], type=g['type'], nl=g['nl'], gold=g['gql'], pred=p,
                      em=exact_match(p, g['gql']), ex=exec_match(p, gold_rows(g['gql']))))


def summ(rows):
    n = len(rows)
    return dict(n=n, EM=round(100 * sum(r['em'] for r in rows) / max(1, n), 2),
                EX=round(100 * sum(r['ex'] for r in rows) / max(1, n), 2))


by_part, by_type = collections.defaultdict(list), collections.defaultdict(list)
for r in items:
    by_part[r['part']].append(r)
    by_type[r['type']].append(r)
res = dict(answers=a.answers, gold=a.gold, missing=sum(1 for g in gold if g['id'] not in ans), **summ(items),
           by_part={k: summ(v) for k, v in sorted(by_part.items())},
           by_type={k: summ(v) for k, v in sorted(by_type.items())}, items=items)
if a.show_wrong:
    for r in items:
        if not (r['em'] and r['ex']):
            print(f"{r['id']} [{r['part']}, loại {r['type']}] EM {r['em']} EX {r['ex']}  {r['nl']}")
            print('    đúng   :', r['gold'])
            print('    trả lời:', r['pred'])
print(f"{a.answers}: {res['n']} câu (thiếu {res['missing']} câu trả lời), EM {res['EM']}  EX {res['EX']}  ({time.time() - t0:.0f} s)")
names = {'A': 'A từ template', 'H': 'H viết tay', 'S': 'S tên thường gọi'}
for k, v in res['by_part'].items():
    print(f"  phần {names.get(k, k):<18} {v['n']:>4} câu  EM {v['EM']:>6}  EX {v['EX']:>6}")
for k, v in res['by_type'].items():
    print(f"  loại {k}                    {v['n']:>4} câu  EM {v['EM']:>6}  EX {v['EX']:>6}")
os.makedirs('work/scores/ask', exist_ok=True)
out = f"work/scores/ask/{os.path.basename(a.answers).rsplit('.', 1)[0]}_{time.strftime('%Y%m%d_%H%M')}.json"
json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('saved', out)
