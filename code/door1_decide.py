# door1_decide.py - step 8d: apply the pre-registered decision rule of door 1 (guide section 3.8).
# Reads the per-question scores of the template-disjoint split (work/scores/door1) and of the random split
# (work/scores/random); reports EM/EX, the drop from random to disjoint, and stratified paired bootstrap 95% intervals
# of the differences between configurations. PRIMARY comparison: ft7_rel vs ft7_none (EX).
# Usage: python code/door1_decide.py      (writes work/logs/door1_decision_<YYYYMMDD_HHMM>.json)
import argparse
import collections
import glob
import json
import os
import random
import time

from common import WORK

ap = argparse.ArgumentParser()
ap.add_argument('--d1', default=WORK + '/scores/door1')
ap.add_argument('--random', default=WORK + '/scores/random')
ap.add_argument('--gold', default=WORK + '/door1/data/test.jsonl')
ap.add_argument('--out', default=WORK + '/logs')
a = ap.parse_args()
SEED, B = 20261004, 10000
RUNS = ['ft7_rel', 'ft7_none', 'ft7_relcn', 'ft7_full', 'icl7']
PRIMARY = ('ft7_rel', 'ft7_none')
SECONDARY = [('ft7_relcn', 'ft7_none'), ('ft7_full', 'ft7_none'), ('ft7_rel', 'ft7_full')]
n_gold = sum(1 for l in open(a.gold, encoding='utf-8') if l.strip())


def load(d):
    R = {}
    for p in glob.glob(os.path.join(d, '*_items.jsonl')):
        name = os.path.basename(p)[:-len('_items.jsonl')]
        if name == 'chatgpt':
            continue
        R[name] = {r['id']: r for r in (json.loads(l) for l in open(p, encoding='utf-8') if l.strip())}
    return R


def acc(rows, k):
    rows = list(rows)
    return round(100 * sum(r[k] for r in rows) / max(1, len(rows)), 2)


def boot(X, Y, k):
    ids = sorted(set(X) & set(Y))
    strata = collections.defaultdict(list)
    for i in ids:
        strata[X[i]['type']].append(X[i][k] - Y[i][k])
    rng = random.Random(SEED)
    n = len(ids)
    point = 100 * sum(sum(v) for v in strata.values()) / n
    stats = []
    for _ in range(B):
        s = 0
        for v in strata.values():
            s += sum(v[rng.randrange(len(v))] for _ in range(len(v)))
        stats.append(100 * s / n)
    stats.sort()
    return dict(n=n, diff=round(point, 2), ci95=[round(stats[int(0.025 * B)], 2), round(stats[int(0.975 * B) - 1], 2)])


D1, RD = load(a.d1), load(a.random)
out = {'n_gold_disjoint': n_gold, 'runs': {}, 'comparisons': {}}
for r in RUNS:
    if r not in D1:
        out['runs'][r] = 'missing'; continue
    x = D1[r]
    e = dict(n=len(x), complete=len(x) == n_gold, EM=acc(x.values(), 'em'), EX=acc(x.values(), 'ex'), by_type={})
    for t in sorted({v['type'] for v in x.values()}):
        e['by_type'][t] = dict(EM=acc((v for v in x.values() if v['type'] == t), 'em'),
                               EX=acc((v for v in x.values() if v['type'] == t), 'ex'))
    if r in RD:
        y = RD[r]
        e['random'] = dict(EM=acc(y.values(), 'em'), EX=acc(y.values(), 'ex'))
        e['drop_random_to_disjoint'] = dict(EM=round(e['random']['EM'] - e['EM'], 2), EX=round(e['random']['EX'] - e['EX'], 2))
        e['drop_by_type_EX'] = {t: round(acc((v for v in y.values() if v['type'] == t), 'ex') - e['by_type'][t]['EX'], 2)
                                for t in e['by_type']}
    out['runs'][r] = e
for (p, q) in [PRIMARY] + SECONDARY:
    if p in D1 and q in D1:
        out['comparisons'][f'{p} - {q}'] = {k: boot(D1[p], D1[q], k) for k in ('ex', 'em')}

p, q = PRIMARY
c = out['comparisons'].get(f'{p} - {q}')
if c is None:
    verdict = 'NOT DECIDABLE: primary runs missing'
else:
    d, lo, hi = c['ex']['diff'], *c['ex']['ci95']
    complete = out['runs'][p]['complete'] and out['runs'][q]['complete']
    if d >= 3 and lo > 0:
        verdict = 'door 1 CLOSED: relevant schema beats no schema by >= 3 EX (CI excludes 0); random-split contradiction = template-leak artefact; paper ablation reproduced -> methods note'
    elif d <= 1:
        verdict = 'door 1 OPEN: no-schema >= relevant-schema - 1 EX also on the disjoint split; contradiction stands (reproducibility finding)'
    else:
        verdict = 'INCONCLUSIVE (pre-registered grey zone): no paper claim'
    if not complete:
        verdict += ' [WARNING: a primary run is incomplete]'
out['primary'] = f'{p} vs {q} (EX, stratified paired bootstrap, B={B}, seed={SEED})'
out['verdict'] = verdict
stamp = time.strftime('%Y%m%d_%H%M')
os.makedirs(a.out, exist_ok=True)
fp = os.path.join(a.out, f'door1_decision_{stamp}.json')
json.dump(out, open(fp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"{'run':<11}{'n':>5}{'EM':>8}{'EX':>8}{'rndEX':>8}{'dropEX':>8}")
for r, e in out['runs'].items():
    if isinstance(e, dict):
        print(f"{r:<11}{e['n']:>5}{e['EM']:>8}{e['EX']:>8}{e.get('random', {}).get('EX', ''):>8}{e.get('drop_random_to_disjoint', {}).get('EX', ''):>8}")
    else:
        print(r, e)
for k, v in out['comparisons'].items():
    print(k, 'EX', v['ex'], 'EM', v['em'])
print('VERDICT:', verdict)
print('saved', fp)
