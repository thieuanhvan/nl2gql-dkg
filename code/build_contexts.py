# build_contexts.py - step 4: write the full schema (with and without Chinese explanations) and the relevant schema of
# every question. Train questions get the GOLD relevant schema (nodes and edges used by the correct query), as in the
# paper; dev/test questions get the schema predicted by the extractor from the question text alone (metrics.py).
# Usage: python code/build_contexts.py [split]     split = data (default, random split) or door1/data (step 8)
# Output: work/schema/schema_full_cn.txt, schema_full.txt; work/<split>_kaggle/{train,dev,test}.jsonl;
#         work/logs/schema_extractor_<split>.json
import collections
import json
import sys

from common import work, read_jsonl, write_jsonl, run
from schema import NODES, render_schema
from metrics import SchemaExtractor, gold_items, render_items

SPLIT = sys.argv[1] if len(sys.argv) > 1 else 'data'
OUT = SPLIT.replace('/', '_').replace('data', 'kaggle') if SPLIT != 'data' else 'data_kaggle'

n2l = collections.defaultdict(set)            # entity name -> labels, read from Neo4j
for lab in NODES:
    for (name,) in run(f'MATCH (n:{lab}) RETURN n.name', timeout=120)[1]:
        if name and len(name) >= 2:
            n2l[name].add(lab)
print('dictionary names', len(n2l), 'ambiguous', sum(1 for v in n2l.values() if len(v) > 1))

open(work('schema', 'schema_full_cn.txt'), 'w', encoding='utf-8').write(render_schema(cn=True))
open(work('schema', 'schema_full.txt'), 'w', encoding='utf-8').write(render_schema(cn=False))

S = {sp: read_jsonl(work(SPLIT, f'{sp}.jsonl')) for sp in ['train', 'dev', 'test']}
ex = SchemaExtractor(n2l, S['train'])
stats = {}
for sp, items in S.items():
    rec, rows = collections.Counter(), []
    for x in items:
        gl, ge = gold_items(x['gql'])
        if sp == 'train':
            pl, pe = gl, ge
        else:
            pl, pe = ex.extract(x['nl'])
            rec['n'] += 1
            rec['all_ok'] += (gl <= pl and ge <= pe)    # every gold item was found
            rec['exact'] += (gl == pl and ge == pe)     # found exactly the gold items
        out = dict(id=x['id'], type=x['type'], type_name=x['type_name'], nl=x['nl'], gql=x['gql'],
                   nl_template=x['nl_template'], gql_template=x['gql_template'], tid=x['tid'],
                   nodes=sorted(pl), edges=[list(e) for e in sorted(pe)],
                   ctx_rel_cn=render_items(pl, pe, cn=True), ctx_rel=render_items(pl, pe, cn=False))
        rows.append(out)                               # no "answer" field: answers never leave this machine
    write_jsonl(work(OUT, f'{sp}.jsonl'), rows)
    stats[sp] = dict(n=len(items))
    if rec['n']:
        stats[sp].update(recall_all=round(rec['all_ok'] / rec['n'], 4), exact=round(rec['exact'] / rec['n'], 4))
json.dump(stats, open(work('logs', f'schema_extractor_{OUT}.json'), 'w', encoding='utf-8'), indent=1)
print(json.dumps(stats, indent=1))
print('written work/' + OUT)
