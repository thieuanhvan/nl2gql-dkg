# ask_build_diabetes.py - build a larger set of NEW questions around Đái tháo đường (diabetes) for "using" the
# fine-tuned model, with gold Cypher checked on Neo4j (only questions whose gold query returns rows are kept).
#   part A: every template and question form of the pool (work/gpt/pool.jsonl), up to 3 bindings each, filled with names linked to Đái tháo đường in the graph
#           (its symptoms, drugs, foods, checks, department, complications), so the questions look like the test set;
#   part H: questions written by hand in everyday style, not from a template;
#   part S: two questions with the everyday name "tiểu đường" (the synonym problem).
# Usage (from the folder that contains code/ and work/; needs the Neo4j password):
#   python code/ask_build_diabetes.py
# Output: demo/diabetes_all_gold.jsonl (id, part, type, nl, gql, n_answer) and a short summary on screen.
import collections
import getpass
import json
import os
import random
import re
import sys

os.environ.setdefault('NL2GQL_LANG', 'vi')
if not os.environ.get('NEO4J_PASSWORD'):
    os.environ['NEO4J_PASSWORD'] = getpass.getpass('Neo4j DBMS password (not echoed): ')
sys.path.insert(0, 'code')
from common import run, read_jsonl  # noqa: E402
from templates import SLOT_LABEL, binding_groups, fill, fmt_num, nonempty, tie_safe  # noqa: E402

DT = 'Đái tháo đường'
FAMILY = [DT, 'Đái tháo đường thai kỳ', 'Bệnh thần kinh do đái tháo đường', 'Nhiễm toan ceton do đái tháo đường',
          'Nhiễm toan lactic do đái tháo đường']
OUT = 'demo'


def bind_diabetes(gql, kw, rng):
    """Fill every slot so that the Disease node of each pattern is a diabetes-family disease."""
    b = {}
    for paths, slots in binding_groups(gql):
        dvars = [v for p in paths for v in re.findall(r'\((\w+):Disease', p)]
        if not dvars:
            return None                                       # pattern without a disease: not about diabetes
        ok = False
        for name in FAMILY:
            conds = [f"{dvars[0]}.name = '{name}'"]
            vs = list(slots)
            for i, a in enumerate(vs):
                for c in vs[:i]:
                    if SLOT_LABEL[slots[a][0]] == SLOT_LABEL[slots[c][0]]:
                        conds.append(f'{a}.name <> {c}.name')
            ret = ', '.join(v + '.name' for v in vs)
            try:
                rows = run(f"MATCH {', '.join(paths)} WHERE {' AND '.join(conds)} RETURN DISTINCT {ret} "
                           f"ORDER BY {ret} LIMIT 200")[1]
            except Exception:
                return None
            rows = [r for r in rows if all(x and "'" not in x and '\\' not in x for x in r)]
            if rows:
                r = rng.choice(rows)
                b.update({slots[v]: r[i] for i, v in enumerate(vs)})
                ok = True
                break
        if not ok:
            return None
    if '[m]' in gql:
        b['m'] = fmt_num(rng.choice(kw['m'])) if kw.get('m') else None
    if '[str]' in gql:
        b['str'] = rng.choice(kw['str']) if kw.get('str') else None
    if None in b.values():
        return None
    return b


def n_rows(q):
    try:
        rows = run(q)[1]
    except Exception:
        return -1
    return len(rows) if nonempty(rows) else 0


TRIES = 3                                                    # different name bindings per question form
rows, seen = [], set()
# part A: templates of the pool, every question form (nl), up to TRIES bindings each
for rec in read_jsonl('work/gpt/pool.jsonl'):
    gql = rec['gql']
    if '[' not in gql:
        continue
    for vi, nl_t in enumerate(rec['nl']):
        rng = random.Random(f"diabetes-{rec['tid']}-{vi}")
        for _ in range(TRIES):
            b = bind_diabetes(gql, rec.get('kw', {}), rng)
            if b is None:
                break
            q, nl = fill(gql, b), fill(nl_t, b)
            if nl in seen or not tie_safe(q):
                continue
            n = n_rows(q)
            if n > 0:
                seen.add(nl)
                rows.append(dict(part='A', type=rec['type'], tid=f"{rec['tid']}_{vi}", nl=nl, gql=q, n_answer=n))

# part H: written by hand, everyday style
D = f"(d:Disease{{name:'{DT}'}})"
HAND = [
    (1, f'{DT} có những triệu chứng gì?', f"MATCH {D}-[:has_symptom]->(s:Symptom) RETURN s.name"),
    (1, f'Người mắc {DT} nên ăn gì?', f"MATCH {D}-[:do_eat]->(f:Food) RETURN f.name"),
    (1, f'Có những món ăn nào được đề xuất cho người bị {DT}?', f"MATCH {D}-[:recommand_eat]->(f:Food) RETURN f.name"),
    (3, f'Thuốc nào được đánh giá tốt để điều trị {DT}?', f"MATCH {D}-[:recommand_drug]->(g:Drug) RETURN g.name"),
    (3, f'{DT} có những biến chứng nào?', f"MATCH {D}-[:acompany_with]->(d2:Disease) RETURN d2.name"),
    (3, f'{DT} thuộc khoa nào?', f"MATCH {D}-[:belongs_to]->(k:Department) RETURN k.name"),
    (1, f'Bị {DT} thì nên đi khám ở khoa nào?', f"MATCH {D} RETURN d.cure_department"),
    (1, f'Tỉ lệ mắc {DT} là bao nhiêu?', f"MATCH {D} RETURN d.get_prob"),
    (1, f'Những ai dễ mắc {DT}?', f"MATCH {D} RETURN d.easy_get"),
    (1, f'{DT} có lây không?', f"MATCH {D} RETURN d.get_way"),
    (1, f'Cách điều trị {DT} là gì?', f"MATCH {D} RETURN d.cure_way"),
    (1, f'Điều trị {DT} mất bao lâu?', f"MATCH {D} RETURN d.cure_lasttime"),
    (1, f'{DT} có được bảo hiểm y tế chi trả không?', f"MATCH {D} RETURN d.yibao_status"),
    (1, f'{DT} có chữa khỏi được không?', f"MATCH {D} RETURN d.cured_prob"),
    (1, f'Chi phí điều trị thấp nhất của {DT} là bao nhiêu?', f"MATCH {D} RETURN d.cost_min"),
    (4, f'Bệnh {DT} có cần làm xét nghiệm Insulin không?',
     f"MATCH {D} OPTIONAL MATCH (d)-[:need_check]->(c:Check{{name:'Insulin'}}) RETURN count(c) > 0"),
    (4, f'Người bị {DT} có phải kiêng Mật ong không?',
     f"MATCH {D} OPTIONAL MATCH (d)-[:no_eat]->(f:Food{{name:'Mật ong'}}) RETURN count(f) > 0"),
    (4, f'{DT} có triệu chứng Khát nước không?',
     f"MATCH {D} OPTIONAL MATCH (d)-[:has_symptom]->(s:Symptom{{name:'Khát nước'}}) RETURN count(s) > 0"),
    (4, f'Người bị {DT} có nên ăn Cà tím không?',
     f"MATCH {D} OPTIONAL MATCH (d)-[:do_eat]->(f:Food{{name:'Cà tím'}}) RETURN count(f) > 0"),
    (6, f'Cần làm bao nhiêu xét nghiệm khi bị {DT}?', f"MATCH {D}-[:need_check]->(c:Check) RETURN count(c)"),
    (6, f'{DT} có bao nhiêu triệu chứng?', f"MATCH {D}-[:has_symptom]->(s:Symptom) RETURN count(s)"),
    (7, f'Ba xét nghiệm đầu tiên cần làm khi bị {DT} là gì?',
     f"MATCH {D}-[r:need_check]->(c:Check) WHERE r.rank <= 3 RETURN c.name"),
    (7, f'Thuốc thường dùng đứng đầu danh sách của {DT} là thuốc nào?',
     f"MATCH {D}-[r:common_drug]->(g:Drug) WHERE r.rank = 1 RETURN g.name"),
    (3, f'Những hãng nào sản xuất thuốc thường dùng cho {DT}?',
     f"MATCH (p:Producer)-[:drugs_of]->(g:Drug)<-[:common_drug]-{D} RETURN p.name"),
    (5, f'Những bệnh nào cùng khoa với {DT}?',
     f"MATCH {D}-[:belongs_to]->(k:Department)<-[:belongs_to]-(d2:Disease) RETURN d2.name"),
    (5, f'{DT} và Tăng huyết áp có chung triệu chứng nào?',
     f"MATCH {D}-[:has_symptom]->(s:Symptom)<-[:has_symptom]-(d2:Disease{{name:'Tăng huyết áp'}}) RETURN s.name"),
    (5, f'Những biến chứng nào của {DT} cần làm xét nghiệm Glucose máu lúc đói?',
     f"MATCH {D}-[:acompany_with]->(d2:Disease)-[:need_check]->(c:Check{{name:'Glucose máu lúc đói'}}) RETURN d2.name"),
    (1, 'Đái tháo đường thai kỳ cần làm những xét nghiệm nào?',
     "MATCH (d:Disease{name:'Đái tháo đường thai kỳ'})-[:need_check]->(c:Check) RETURN c.name"),
    (1, 'Bệnh thần kinh do đái tháo đường có những triệu chứng nào?',
     "MATCH (d:Disease{name:'Bệnh thần kinh do đái tháo đường'})-[:has_symptom]->(s:Symptom) RETURN s.name"),
    (8, f'Những thuốc thường dùng của {DT} có tên chứa "metformin"?',
     f"MATCH {D}-[:common_drug]->(g:Drug) WHERE lower(g.name) CONTAINS 'metformin' RETURN g.name"),
]
for typ, nl, q in HAND:
    n = n_rows(q)
    if n > 0 and nl not in seen:
        seen.add(nl)
        rows.append(dict(part='H', type=typ, tid='hand', nl=nl, gql=q, n_answer=n))
    else:
        print('bỏ (rỗng hoặc lỗi):', nl)

# part S: everyday name, gold uses the real node name
for typ, nl, q in [(3, 'Bệnh tiểu đường cần làm những xét nghiệm nào?', f"MATCH {D}-[:need_check]->(c:Check) RETURN c.name"),
                   (3, 'Người bị tiểu đường nên kiêng ăn gì?', f"MATCH {D}-[:no_eat]->(f:Food) RETURN f.name")]:
    rows.append(dict(part='S', type=typ, tid='alias', nl=nl, gql=q, n_answer=n_rows(q)))

for i, r in enumerate(rows, 1):
    r['id'] = f'D{i:03d}'
os.makedirs(OUT, exist_ok=True)
with open(f'{OUT}/diabetes_all_gold.jsonl', 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(dict(id=r['id'], **{k: v for k, v in r.items() if k != 'id'}), ensure_ascii=False) + '\n')
c = collections.Counter((r['part'], r['type']) for r in rows)
print('câu theo phần:', dict(collections.Counter(r['part'] for r in rows)))
print('phần A theo loại:', {t: c[('A', t)] for t in range(1, 9)})
print('tổng', len(rows), 'câu ->', f'{OUT}/diabetes_all_gold.jsonl')
