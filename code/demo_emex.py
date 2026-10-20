# demo_emex.py - short live demo of EM and EX on Neo4j for three test questions of one configuration
# (default ft7_relcn): one right on both metrics, one wrong on EM but right on EX (same answer, different text),
# one wrong on both. Prints the record counts first, then for each question: relevant schema, gold and predicted
# Cypher, the clause sets EM compares, the rows EX compares. With --all it re-scores all 296 test questions and
# prints the elapsed time.
# Usage (from the folder that contains code/ and work/; Vietnamese data, NL2GQL_LANG=vi):
#   python code/demo_emex.py                      three questions, ft7_relcn
#   python code/demo_emex.py --job ft7_full --ids test_0107 test_0161
#   python code/demo_emex.py --all                also EM/EX of the whole test set (about 1 minute)
import argparse
import getpass
import json
import os
import sys
import time

os.environ.setdefault('NL2GQL_LANG', 'vi')
if not os.environ.get('NEO4J_PASSWORD'):
    os.environ['NEO4J_PASSWORD'] = getpass.getpass('Neo4j DBMS password (not echoed): ')
from common import work, read_jsonl, run  # noqa: E402
from metrics import em_components, exact_match, exec_match, gold_rows  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--job', default='ft7_relcn')
ap.add_argument('--ids', nargs='*', default=['test_0107', 'test_0161', 'test_0108'])
ap.add_argument('--all', action='store_true')
a = ap.parse_args()
LINE = '=' * 100


def show_rows(q, k=6):
    try:
        cols, rows = run(q)
    except Exception as e:
        print(f'    -> lỗi khi chạy: {str(e).splitlines()[0][:160]}')
        return
    print(f'    -> {len(rows)} dòng' + (f', {k} dòng đầu:' if len(rows) > k else ':'))
    for r in rows[:k]:
        print('       ', r)


def show_clauses(q):
    for k, el in em_components(q):
        print(f'       {k:<15}', sorted(x for x, _ in el))


print(LINE)
print('SỐ RECORDS')
t0 = time.time()
for lab, n in run('MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC')[1]:
    print(f'  node {lab:<12} {n:>8,}')
for rel, n in run('MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC')[1]:
    print(f'  cạnh {rel:<16} {n:>8,}')
for sp in ('train', 'dev', 'test'):
    print(f'  {sp:<5} {len(read_jsonl(work("data", sp + ".jsonl"))):>5} cặp (câu hỏi, Cypher)')

gold = {g['id']: g for g in read_jsonl(work('data_kaggle', 'test.jsonl'))}
preds = {r['id']: r.get('pred') or '' for r in read_jsonl(work('out', 'random', 'preds', a.job + '.jsonl'))}
for i in a.ids:
    g, p = gold[i], preds.get(i, '')
    print(LINE)
    print(f'{i}  loại {g["type"]} ({g["type_name"]})')
    print('  Câu hỏi        :', g['nl'])
    print('  Schema liên quan: nodes', g['nodes'], '| edges', [e[0] for e in g['edges']])
    print('  Cypher đúng    :', g['gql'])
    print(f'  Cypher {a.job:<9}:', p)
    print('  EM so tập thành phần từng mệnh đề (biến đã đổi tên v0, v1, ...):')
    print('    đúng:'); show_clauses(g['gql'])
    print('    dự đoán:'); show_clauses(p)
    print('  EX chạy cả hai câu trên Neo4j:')
    print('    đúng:'); show_rows(g['gql'])
    print('    dự đoán:'); show_rows(p)
    print(f'  ==> EM = {exact_match(p, g["gql"])}   EX = {exec_match(p, gold_rows(g["gql"]))}')

if a.all:
    print(LINE)
    t1 = time.time()
    em = ex = 0
    for i, g in gold.items():
        em += exact_match(preds.get(i, ''), g['gql'])
        ex += exec_match(preds.get(i, ''), gold_rows(g['gql']))
    n = len(gold)
    print(f'{a.job}: {n} câu, EM {100 * em / n:.2f}  EX {100 * ex / n:.2f}  ({time.time() - t1:.0f} s)')
print(LINE)
print(f'xong ({time.time() - t0:.0f} s)')
