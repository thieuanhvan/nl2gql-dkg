# score.py - steps 7, 8 and 9: EM and EX of prediction files on Neo4j.
# Usage:
#   python code/score.py --gold-sanity                          gold vs gold, must give EM 100 / EX 100
#   python code/score.py --preds work/out/random/preds          one <job>.jsonl per configuration (Kaggle output)
#   python code/score.py --split door1 --preds work/out/door1/preds
#   python code/score.py --chatgpt work/chatgpt_50questions/answers_chatgpt.txt     (step 9, lines "Qxx: <query>")
# Output: work/scores/<split>/scores_<YYYYMMDD_HHMM>.json and <job>_items.jsonl (score of every question).
import argparse
import collections
import glob
import json
import os
import re
import time

from common import work, read_jsonl, write_jsonl, TYPE_NAME
from metrics import exact_match, exec_match, gold_rows

ap = argparse.ArgumentParser()
ap.add_argument('--split', choices=['random', 'door1'], default='random')
ap.add_argument('--preds', help='folder with <job>.jsonl files, or one .jsonl file')
ap.add_argument('--gold-sanity', action='store_true')
ap.add_argument('--chatgpt', help='answers file of the 50-question sheet')
a = ap.parse_args()

gold = read_jsonl(work('data' if a.split == 'random' else 'door1/data', 'test.jsonl'))
cache = {}


def score(preds, items):
    res = []
    for g in items:
        p = preds.get(g['id'], '')          # a missing prediction counts as wrong
        if g['id'] not in cache:
            cache[g['id']] = gold_rows(g['gql'])
        res.append(dict(id=g['id'], type=g['type'], em=exact_match(p, g['gql']), ex=exec_match(p, cache[g['id']])))
    n = len(res)
    out = dict(n=n, EM=round(100 * sum(r['em'] for r in res) / max(1, n), 2),
               EX=round(100 * sum(r['ex'] for r in res) / max(1, n), 2), by_type={})
    by = collections.defaultdict(list)
    for r in res:
        by[r['type']].append(r)
    for t in sorted(by):
        v = by[t]
        out['by_type'][f'{t} {TYPE_NAME[t]}'] = dict(n=len(v), EM=round(100 * sum(r['em'] for r in v) / len(v), 2),
                                                     EX=round(100 * sum(r['ex'] for r in v) / len(v), 2))
    return out, res


table, outdir = {}, work('scores', a.split, 'x').rsplit('/', 1)[0]
if a.gold_sanity:
    table['gold_vs_gold'], _ = score({g['id']: g['gql'] for g in gold}, gold)
if a.preds:
    files = sorted(glob.glob(os.path.join(a.preds, '*.jsonl'))) if os.path.isdir(a.preds) else [a.preds]
    for fp in files:
        preds = {r['id']: r.get('pred', '') for r in read_jsonl(fp)}
        name = os.path.basename(fp)[:-6]
        table[name], rows = score(preds, gold)
        write_jsonl(f'{outdir}/{name}_items.jsonl', rows)
if a.chatgpt:
    qs = read_jsonl(work('chatgpt_50questions', 'questions_50.jsonl'))
    qmap = {q['q']: q['id'] for q in qs}
    preds, cur = {}, None
    for line in open(a.chatgpt, encoding='utf-8').read().replace('```cypher', '').replace('```', '').splitlines():
        m = re.match(r'\s*\**\s*Q(\d{1,2})\s*\**\s*[:：.]\s*(.*)$', line)
        if m:
            cur = 'Q%02d' % int(m.group(1))
            preds[qmap.get(cur, cur)] = m.group(2).strip()
        elif cur and line.strip():
            preds[qmap.get(cur, cur)] += ' ' + line.strip()      # an answer may continue on the next line
    ids = set(qmap.values())
    table['chatgpt'], rows = score(preds, [g for g in gold if g['id'] in ids])
    table['chatgpt']['missing_answers'] = sorted(q for q, i in qmap.items() if i not in preds)
    write_jsonl(f'{outdir}/chatgpt_items.jsonl', rows)
    for p in sorted(glob.glob(f'{outdir}/*_items.jsonl')):  # the other configurations on the same 50 questions
        name = os.path.basename(p)[:-12]
        if name != 'chatgpt':
            r = [x for x in read_jsonl(p) if x['id'] in ids]
            table[f'{name} (same 50)'] = dict(n=len(r), EM=round(100 * sum(x['em'] for x in r) / max(1, len(r)), 2),
                                              EX=round(100 * sum(x['ex'] for x in r) / max(1, len(r)), 2))
json.dump(table, open(f'{outdir}/scores_{time.strftime("%Y%m%d_%H%M")}.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(f"{'run':<22}{'n':>5}{'EM':>8}{'EX':>8}")
for k, v in table.items():
    print(f"{k:<22}{v['n']:>5}{v['EM']:>8}{v['EX']:>8}")
