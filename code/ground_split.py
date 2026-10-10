# ground_split.py - step 3f (paper Sec. 4.1, grounding): fill the slots of every pool pair with real names sampled from
# Neo4j, run the query, keep only instances that run, return rows, are not duplicates and have no tie at the
# ORDER BY ... LIMIT cut; balance yes/no answers of type 4; pick the same number per type; split 7:1:2 per type.
# All sampling queries use ORDER BY and a fixed seed, so the same pool always gives the same data set.
# Output: work/data/{train,dev,test}.jsonl, work/data/pool.jsonl, work/logs/generation_summary.json.
# Usage: python code/ground_split.py [--per-type 188]
import argparse
import collections
import json
import time

from common import work, read_jsonl, write_jsonl, rng_for, run, TYPE_NAME
from templates import (SLOT_LABEL, binding_groups, bind_group, fill, fmt_num, nonempty, tie_safe, norm_answer,
                       entity_pool)

ap = argparse.ArgumentParser()
ap.add_argument('--per-type', type=int, default=188)
ap.add_argument('--tries', type=int, default=12, help='grounding attempts per question')
a = ap.parse_args()

pool = read_jsonl(work('gpt', 'pool.jsonl'))
t0 = time.time()
cands, stats = collections.defaultdict(list), collections.Counter()
for rec in pool:
    gql, kw = rec['gql'], rec.get('kw', {})
    for vi, nl_t in enumerate(rec['nl']):
        tid = f"{rec['tid']}_{vi}"
        rng = rng_for('ground', tid)
        seen = set()
        for _ in range(a.tries):
            b, ok = {}, True
            unbound = rec['type'] == 4 and 'OPTIONAL MATCH' in gql and rng.random() < 0.5
            for paths, slots in binding_groups(gql):
                if unbound and len(slots) > 1:          # yes/no questions also need "no" answers
                    for v, s in slots.items():
                        b[s] = rng.choice(entity_pool(SLOT_LABEL[s[0]]))
                    continue
                r = bind_group(paths, slots, rng)
                if r is None:
                    ok = False
                    break
                b.update(r)
            if not ok:
                stats['bind_fail'] += 1
                continue
            if '[m]' in gql:
                b['m'] = fmt_num(rng.choice(kw['m']))
            if '[str]' in gql:
                b['str'] = rng.choice(kw['str'])
            q, nl = fill(gql, b), fill(nl_t, b)
            if nl in seen:
                stats['dup'] += 1
                continue
            seen.add(nl)
            try:
                _, rows = run(q)
            except Exception:
                stats['exec_error'] += 1
                continue
            if not nonempty(rows):
                stats['empty'] += 1
                continue
            if not tie_safe(q):
                stats['tie'] += 1
                continue
            ans = norm_answer(rows)
            cands[rec['type']].append(dict(nl=nl, gql=q, nl_template=nl_t, gql_template=gql, type=rec['type'],
                                           type_name=TYPE_NAME[rec['type']], tid=tid, round=rec['round'],
                                           source=rec.get('source', ''), bindings=b, answer=ans[:200], n_answer=len(rows)))
            stats['kept'] += 1
print('grounding', dict(stats), round(time.time() - t0), 's', flush=True)

rng = rng_for('select')
final = []
for typ in sorted(cands):
    by_t = collections.defaultdict(list)
    for c in cands[typ]:
        by_t[c['tid']].append(c)
    keys = sorted(by_t)
    rng.shuffle(keys)
    if typ == 4:   # put "no" answers first so that yes and no are balanced
        for k in keys:
            by_t[k].sort(key=lambda c: 0 if c['answer'][0][0] is False else 1)
    pick, i = [], 0
    while len(pick) < a.per_type and any(by_t[k] for k in keys):
        k = keys[i % len(keys)]
        if by_t[k]:
            pick.append(by_t[k].pop(0))
        i += 1
    final.extend(pick)
    print(f'type {typ}: candidates {len(cands[typ])}, picked {len(pick)}, templates {len(keys)}')

splits = {'train': [], 'dev': [], 'test': []}
for typ in sorted({c['type'] for c in final}):
    items = [c for c in final if c['type'] == typ]
    rng.shuffle(items)
    n = len(items)
    ntr, ndv = round(n * 0.7), round(n * 0.1)
    splits['train'] += items[:ntr]
    splits['dev'] += items[ntr:ntr + ndv]
    splits['test'] += items[ntr + ndv:]
for sp, items in splits.items():
    for i, c in enumerate(items):
        c['id'] = f'{sp}_{i:04d}'
    write_jsonl(work('data', f'{sp}.jsonl'), items)
write_jsonl(work('data', 'pool.jsonl'), pool)
summary = dict(pool=len(pool), pool_by_source=dict(collections.Counter(p.get('source', '') for p in pool)),
               grounding=dict(stats), sizes={sp: len(v) for sp, v in splits.items()},
               per_type={sp: dict(sorted(collections.Counter(c['type'] for c in v).items())) for sp, v in splits.items()},
               type4_answers=dict(collections.Counter(str(c['answer'][0][0]) for c in final if c['type'] == 4)))
json.dump(summary, open(work('logs', 'generation_summary.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
