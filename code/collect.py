# collect.py - step 3c: read ChatGPT's replies of one round and check every NL-GQL pair: JSON format, slots,
# labels/relationships/properties of the schema, Cypher syntax by Neo4j EXPLAIN, duplicates. Pairs that pass get a
# CoT prompt (paper Sec. 4.1): ChatGPT explains each clause of the query, then rewrites the question.
# Output: work/gpt/candidates/round<R>.jsonl (rejected pairs carry the reason in "problems") and
#         work/gpt/prompts/cot_round<R>_part<k>.txt (40 queries per prompt).
# Usage: python code/collect.py --round 1
import argparse
import collections
import os
import re

from common import LANG, work, read_jsonl, write_jsonl
from schema import render_schema
from templates import TYPE_DESC, parse_json_lines, schema_problems, explain_template

ap = argparse.ArgumentParser()
ap.add_argument('--round', type=int, required=True)
ap.add_argument('--batch', type=int, default=40, help='queries per CoT prompt')
a = ap.parse_args()


def norm(g):
    return re.sub(r'\s+', ' ', g.strip().rstrip(';'))


pool = read_jsonl(work('gpt', 'pool.jsonl'))
seen = {norm(p['gql']) for p in pool}
cands, stats = [], collections.Counter()
for t in sorted(TYPE_DESC):
    rf = work('gpt', 'responses', f'round{a.round}_type{t}.txt')
    if not os.path.exists(rf):
        print('missing reply file:', rf)
        stats['missing_reply'] += 1
        continue
    for i, o in enumerate(parse_json_lines(open(rf, encoding='utf-8').read())):
        stats['parsed'] += 1
        nls = o.get('nl')
        nls = [nls] if isinstance(nls, str) else [x for x in (nls or []) if isinstance(x, str) and x.strip()]
        gql = norm(str(o.get('gql', '')))
        kw = {k: o[k] for k in ('m', 'str') if isinstance(o.get(k), list) and o[k]}
        rec = dict(tid=f'G{a.round}_{t}_{i:02d}', type=t, round=a.round, source='chatgpt', nl=nls, gql=gql, kw=kw)
        probs = [] if nls else ['no NL']
        for nl in nls:
            probs += schema_problems(nl, gql, kw)
        if not probs:
            ok, err = explain_template(gql, kw)
            if not ok:
                probs.append('Neo4j: ' + err)
        if not probs and gql in seen:
            probs.append('duplicate of an earlier pair')
        rec['problems'] = sorted(set(probs))
        stats['rejected' if probs else 'passed'] += 1
        if not probs:
            seen.add(gql)
        cands.append(rec)
write_jsonl(work('gpt', 'candidates', f'round{a.round}.jsonl'), cands)

ok = [c for c in cands if not c['problems']]
schema = render_schema(cn=True)
n_parts = 0
for k in range(0, len(ok), a.batch):
    n_parts += 1
    items = '\n'.join('{"id": "%s", "gql": "%s"}' % (c['tid'], c['gql'].replace('\\', '\\\\').replace('"', '\\"'))
                      for c in ok[k:k + a.batch])
    if LANG == 'vi':
        prompt = ('Bạn là chuyên gia truy vấn CSDL đồ thị. Dưới đây là schema của một đồ thị tri thức về bệnh (Neo4j, Cypher); '
                  'mỗi trường có kèm giải thích tiếng Việt.\n\n'
                  f'[Schema]\n{schema}\n\n'
                  'Mỗi dòng dưới đây là một template truy vấn Cypher; chỗ trống trong ngoặc vuông như [d], [s], [m] là thực thể '
                  'hay con số sẽ điền sau.\n'
                  'Với mỗi truy vấn: trước hết giải thích từng mệnh đề (MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT) đang làm gì, '
                  'rồi dựa vào lời giải thích đó viết một câu hỏi tiếng Việt mà truy vấn trả lời, giữ nguyên các chỗ trống.\n\n'
                  f'[Truy vấn]\n{items}\n\n'
                  'Chỉ xuất JSON, mỗi dòng một đối tượng, theo đúng thứ tự đầu vào, không đánh số. Định dạng:\n'
                  '{"id": "G1_1_00", "cot": "giải thích từng bước", "nl": "câu hỏi viết lại"}\n')
        open(work('gpt', 'prompts', f'cot_round{a.round}_part{n_parts}.txt'), 'w', encoding='utf-8').write(prompt)
        continue
    prompt = ('你是图数据库查询专家。下面是一个疾病知识图谱（Neo4j，Cypher）的 schema，每个字段后附有中文解释。\n\n'
              f'[Schema]\n{schema}\n\n'
              '下面每行是一个 Cypher 查询模板，方括号槽位如 [d]、[s]、[m] 表示待填的实体或数值。\n'
              '对每个查询：先按子句（MATCH、WHERE、WITH、RETURN、ORDER BY、LIMIT）逐步解释它在做什么，'
              '再根据你的解释写出一个它所回答的中文自然语言问题，问题中保留完全相同的槽位。\n\n'
              f'[查询]\n{items}\n\n'
              '只输出 JSON，每行一个对象，按输入顺序，不要编号。格式：\n'
              '{"id": "G1_1_00", "cot": "逐步解释", "nl": "改写后的问题"}\n')
    open(work('gpt', 'prompts', f'cot_round{a.round}_part{n_parts}.txt'), 'w', encoding='utf-8').write(prompt)
print(dict(stats))
print('passed per type', dict(sorted(collections.Counter(c['type'] for c in ok).items())))
reasons = collections.Counter(' '.join(p.split(' ')[:2]) for c in cands for p in c['problems'])
print('main rejection reasons', reasons.most_common(8))
print(f'{n_parts} CoT prompt file(s): work/gpt/prompts/cot_round{a.round}_part<k>.txt; '
      f'save each reply as work/gpt/responses/cot_round{a.round}_part<k>.txt')
