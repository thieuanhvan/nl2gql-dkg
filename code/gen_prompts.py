# gen_prompts.py - step 3a (paper Sec. 4.1, self-instruct): write one ChatGPT prompt per question type.
# The pool starts with the 64 seed pairs of code/seeds.jsonl (8 per type); each round shows ChatGPT K = 8 pairs of the
# same type from the pool and asks for 12 new ones. Prompts go to work/gpt/prompts/, and the file names for
# ChatGPT's replies are listed in work/gpt/prompts/round<R>_README.txt.
# Usage: python code/gen_prompts.py --round 1     (then --round 2 after step 3e of round 1)
import argparse
import json
import os

from common import ROOT, LANG, work, read_jsonl, write_jsonl, rng_for, TYPE_NAME
from schema import render_schema
from templates import TYPE_DESC, SLOT_RULES

ap = argparse.ArgumentParser()
ap.add_argument('--round', type=int, required=True)
ap.add_argument('--new', type=int, default=12, help='new pairs asked per type')
ap.add_argument('--k', type=int, default=8, help='examples shown per prompt (paper: K = 8)')
a = ap.parse_args()

pool_file = work('gpt', 'pool.jsonl')
pool = read_jsonl(pool_file)
if not pool:
    for i, s in enumerate(read_jsonl(ROOT + ('/code/seeds_vi.jsonl' if LANG == 'vi' else '/code/seeds.jsonl'))):
        kw = {k: s[k] for k in ('m', 'str') if k in s}
        pool.append(dict(tid=f'S{s["type"]}_{i:03d}', type=s['type'], round=0, source='seed', nl=s['nl'], gql=s['gql'], kw=kw))
    write_jsonl(pool_file, pool)
    print(f'pool started with {len(pool)} seed pairs')

schema = render_schema(cn=True)
readme = [f'Round {a.round}: paste each prompt into a NEW ChatGPT chat and save the whole reply as the reply file.', '']
for t in sorted(TYPE_DESC):
    same = [p for p in pool if p['type'] == t]
    demos = rng_for('demo', a.round, t).sample(same, min(a.k, len(same)))
    lines = []
    for d in demos:
        obj = {'nl': d['nl'], 'gql': d['gql']}
        obj.update({k: v for k, v in d.get('kw', {}).items() if v})
        lines.append(json.dumps(obj, ensure_ascii=False))
    if LANG == 'vi':
        prompt = (
            'Bạn là chuyên gia truy vấn CSDL đồ thị. Dưới đây là schema của một đồ thị tri thức về bệnh (CSDL Neo4j, truy vấn bằng '
            'Cypher); mỗi trường có kèm giải thích tiếng Việt.\n\n'
            f'[Schema]\n{schema}\n\n'
            f'[Loại câu hỏi {t}: {TYPE_NAME[t]}]\n{TYPE_DESC[t]}\n\n'
            f'[Quy ước chỗ trống]\n{SLOT_RULES}\n\n'
            '[Ví dụ] (mỗi dòng một đối tượng JSON)\n' + '\n'.join(lines) + '\n\n'
            f'[Nhiệm vụ]\nTheo các ví dụ, viết thêm {a.new} cặp template NL-GQL mới cho cùng loại câu hỏi, khác nhau và không trùng ví dụ. Yêu cầu:\n'
            '1. GQL viết bằng Cypher, chỉ dùng nhãn, quan hệ và thuộc tính có trong schema ở trên; truy vấn phải chạy được trên CSDL.\n'
            '2. Mỗi template cho 1 đến 2 cách hỏi tự nhiên bằng tiếng Việt, đặt trong danh sách "nl".\n'
            '3. Nếu dùng [m] thì cho 2 đến 4 con số phù hợp trong "m"; nếu dùng [str] thì cho 2 đến 4 chuỗi con phù hợp '
            '(bằng tiếng Việt, đúng như tên trong CSDL) trong "str".\n'
            '4. Chỉ xuất JSON, mỗi dòng một đối tượng, không đánh số, không giải thích. Định dạng:\n'
            '{"nl": ["cách hỏi 1", "cách hỏi 2"], "gql": "MATCH ...", "m": [3, 5]}\n')
    else:
        prompt = (
        '你是图数据库查询专家。下面是一个疾病知识图谱（Neo4j 数据库，用 Cypher 查询）的 schema，每个字段后面附有中文解释。\n\n'
        f'[Schema]\n{schema}\n\n'
        f'[问题类型 {t}：{TYPE_NAME[t]}]\n{TYPE_DESC[t]}\n\n'
        f'[槽位约定]\n{SLOT_RULES}\n\n'
        '[示例]（每行一个 JSON 对象）\n' + '\n'.join(lines) + '\n\n'
        f'[任务]\n参照示例，为同一问题类型再写 {a.new} 个新的 NL-GQL 模板对，彼此不同，也不要与示例重复。要求：\n'
        '1. GQL 用 Cypher，只能使用上面 schema 中的标签、关系和属性；查询要能在数据库中执行。\n'
        '2. 每个模板给 1 到 2 种自然的中文问法，放在 "nl" 列表中。\n'
        '3. 用到 [m] 时在 "m" 中给出 2 到 4 个合适的数字；用到 [str] 时在 "str" 中给出 2 到 4 个合适的子字符串。\n'
        '4. 只输出 JSON，每行一个对象，不要编号，不要解释。格式：\n'
        '{"nl": ["问法1", "问法2"], "gql": "MATCH ...", "m": [3, 5]}\n')
    pf = work('gpt', 'prompts', f'round{a.round}_type{t}.txt')
    open(pf, 'w', encoding='utf-8').write(prompt)
    rf = work('gpt', 'responses', f'round{a.round}_type{t}.txt')
    readme.append(f'type {t} ({TYPE_NAME[t]}): prompt {os.path.basename(pf)}  ->  reply work/gpt/responses/{os.path.basename(rf)}')
open(work('gpt', 'prompts', f'round{a.round}_README.txt'), 'w', encoding='utf-8').write('\n'.join(readme) + '\n')
print('\n'.join(readme))
