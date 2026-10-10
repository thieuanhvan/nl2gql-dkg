# cot_check.py - step 3e (paper Sec. 4.1, CoT GQL-to-NL check): compare ChatGPT's rewritten question with each original
# question of the pair; keep a question if the cosine similarity of their sentence embeddings is at least 0.8 (the
# paper's threshold). Pairs with at least one kept question join the pool. Model: paraphrase-multilingual-MiniLM-L12-v2
# (the questions are Chinese). Report per pair: work/gpt/candidates/cot_round<R>.jsonl.
# Usage: python code/cot_check.py --round 1
import argparse
import collections
import glob
import os
import sys

from common import WORK, work, read_jsonl, write_jsonl
from templates import parse_json_lines

ap = argparse.ArgumentParser()
ap.add_argument('--round', type=int, required=True)
ap.add_argument('--threshold', type=float, default=0.8)
a = ap.parse_args()

cands = [c for c in read_jsonl(work('gpt', 'candidates', f'round{a.round}.jsonl')) if not c['problems']]
replies = {}
for pf in sorted(glob.glob(f'{WORK}/gpt/prompts/cot_round{a.round}_part*.txt')):
    rf = work('gpt', 'responses', os.path.basename(pf))
    if not os.path.exists(rf):
        sys.exit(f'missing reply file: {rf}')
    for o in parse_json_lines(open(rf, encoding='utf-8').read()):
        if o.get('id') and isinstance(o.get('nl'), str):
            replies[o['id']] = o

from sentence_transformers import SentenceTransformer, util  # noqa: E402
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

report, accepted, stats = [], [], collections.Counter()
for c in cands:
    r = replies.get(c['tid'])
    if r is None:
        stats['no_reply'] += 1
        report.append(dict(tid=c['tid'], type=c['type'], status='no reply'))
        continue
    emb = model.encode([r['nl']] + c['nl'], convert_to_tensor=True, normalize_embeddings=True)
    sims = [round(float(util.cos_sim(emb[0], emb[i + 1])), 4) for i in range(len(c['nl']))]
    keep = [nl for nl, s in zip(c['nl'], sims) if s >= a.threshold]
    report.append(dict(tid=c['tid'], type=c['type'], gql=c['gql'], nl=c['nl'], cot=r.get('cot', ''), rewritten=r['nl'],
                       sims=sims, kept=keep))
    if keep:
        accepted.append(dict({k: v for k, v in c.items() if k != 'problems'}, nl=keep))
        stats['accepted'] += 1
    else:
        stats['rejected_low_similarity'] += 1
write_jsonl(work('gpt', 'candidates', f'cot_round{a.round}.jsonl'), report)

pool = read_jsonl(work('gpt', 'pool.jsonl'))
have = {p['tid'] for p in pool}
pool += [x for x in accepted if x['tid'] not in have]
write_jsonl(work('gpt', 'pool.jsonl'), pool)
print(dict(stats))
print('pool size', len(pool), 'per type', dict(sorted(collections.Counter(p['type'] for p in pool).items())))
