# door1_split.py - step 8a ("door 1"): split the SAME questions again so that no query template of the test set
# appears in train or dev. Group = template family (tid without the question-variant suffix): all questions made from
# one template go to the same part. Per type, families are chosen so that test and dev get 20% and 10% of the
# questions (seeded shuffles + greedy fill); the rest is train. Pre-registered rule: guide section 3.8.
# Output: work/door1/data/{train,dev,test}.jsonl, work/logs/door1_split.json. Usage: python code/door1_split.py
import collections
import json
import random
import re

from common import work, read_jsonl, write_jsonl

SEED = 20261004
MAX_TRIES = 200000

A = []
for sp in ['train', 'dev', 'test']:
    for x in read_jsonl(work('data', f'{sp}.jsonl')):
        x['orig_split'] = sp
        x['orig_id'] = x['id']
        A.append(x)
fam_of = lambda x: x['tid'].rsplit('_', 1)[0]


def pick(fams, sizes, target, rng):
    """First exact subset found over seeded shuffles + greedy fill. If the target is not reachable,
    the closest reachable count (ties -> smaller) becomes the target."""
    reach = {0}
    for f in fams:
        reach |= {r + sizes[f] for r in reach}
    if target not in reach:
        target = min(reach, key=lambda r: (abs(r - target), r))
    for _ in range(MAX_TRIES):
        order = fams[:]; rng.shuffle(order)
        tot, sel = 0, []
        for f in order:
            if tot + sizes[f] <= target:
                sel.append(f); tot += sizes[f]
            if tot == target:
                return sel, tot
    raise SystemExit(f'no subset of size {target} found')


rng = random.Random(SEED)
assign, report = {}, {'seed': SEED, 'per_type': {}}
by_type = collections.defaultdict(lambda: collections.Counter())
for x in A:
    by_type[x['type']][fam_of(x)] += 1
for t in sorted(by_type):
    sizes = by_type[t]
    fams = sorted(sizes)
    n_test, n_dev = round(0.2 * sum(sizes.values())), round(0.1 * sum(sizes.values()))   # same 7:1:2 as step 3
    te, nte = pick(fams, sizes, n_test, rng)
    rest = [f for f in fams if f not in te]
    dv, ndv = pick(rest, sizes, n_dev, rng)
    for f in fams:
        assign[f] = 'test' if f in te else 'dev' if f in dv else 'train'
    report['per_type'][t] = dict(families=len(fams), items=sum(sizes.values()),
                                 test_families=len(te), test_items=nte, dev_families=len(dv), dev_items=ndv,
                                 train_families=len(fams) - len(te) - len(dv),
                                 train_items=sum(sizes.values()) - nte - ndv,
                                 target_test=n_test, target_dev=n_dev)

S = {'train': [], 'dev': [], 'test': []}
for x in sorted(A, key=lambda x: (x['type'], x['orig_split'], x['orig_id'])):
    S[assign[fam_of(x)]].append(x)
for sp, items in S.items():
    rows = []
    for i, x in enumerate(items):
        x = dict(x)
        x['id'] = f'd1_{sp}_{i:04d}'
        rows.append(x)
    write_jsonl(work('door1', 'data', f'{sp}.jsonl'), rows)


def skeleton(g):
    g = re.sub(r"'[^']*'", "'V'", g)
    g = re.sub(r'\b\d+(\.\d+)?\b', 'N', g)
    g = re.sub(r':\s*\w+', ':L', g)
    g = re.sub(r'\.\s*[A-Za-z_]\w*', '.P', g)
    return re.sub(r'\s+', ' ', g).strip()


def overlap(key, a, b):
    ka = {key(x) for x in S[a]}
    return sum(key(x) in ka for x in S[b])

report['sizes'] = {sp: len(v) for sp, v in S.items()}
report['families'] = {sp: len({fam_of(x) for x in v}) for sp, v in S.items()}
report['test_items_with_gql_template_in_train'] = overlap(lambda x: x['gql_template'], 'train', 'test')
report['test_items_with_gql_template_in_dev'] = overlap(lambda x: x['gql_template'], 'dev', 'test')
report['dev_items_with_gql_template_in_train'] = overlap(lambda x: x['gql_template'], 'train', 'dev')
report['test_items_with_nl_template_in_train'] = overlap(lambda x: x['nl_template'], 'train', 'test')
report['test_items_with_nl_template_in_train_or_dev'] = sum(
    x['nl_template'] in {y['nl_template'] for y in S['train'] + S['dev']} for x in S['test'])
report['diagnostic_test_items_with_gql_skeleton_in_train'] = overlap(lambda x: skeleton(x['gql_template']), 'train', 'test')
report['diagnostic_test_skeletons_distinct'] = len({skeleton(x['gql_template']) for x in S['test']})
report['test_per_type'] = dict(sorted(collections.Counter(x['type'] for x in S['test']).items()))
report['test_from_orig_split'] = dict(collections.Counter(x['orig_split'] for x in S['test']))
json.dump(report, open(work('logs', 'door1_split.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(report, ensure_ascii=False, indent=1))
