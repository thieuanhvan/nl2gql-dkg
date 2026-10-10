# build_kg.py - step 2: load DiseaseKG (medical.json of liuhuanyong/QASystemOnMedicalKG) into an EMPTY Neo4j database.
# Same graph as build_medicalgraph.py of the original repository:
#   nodes Disease, Drug, Food, Check, Department, Producer, Symptom (key: name)
#   relationships recommand_eat, no_eat, do_eat, common_drug, recommand_drug, need_check, has_symptom, acompany_with,
#   belongs_to (Disease->Department and Department->Department), drugs_of (Producer->Drug); property name = Chinese label
# Additions needed by the numeric question types 2, 4, 6, 7 of the paper:
#   Disease numbers parsed from text: get_prob_pct, cured_prob_pct, cure_days, cost_min, cost_max
#   relationship property rank = position (1, 2, ...) of the item in the source list
# Field 'desc' is renamed 'description' because DESC is a Cypher keyword. Empty text becomes "no value" (null).
# Usage: python code/build_kg.py      (writes work/logs/kg_stats.json)
import json
import re
import sys
import time

from common import ROOT, work, session

SRC = ROOT + '/data/medical.json'


def pct(s):
    m = re.search(r'([\d.]+)\s*%', s or '')
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


UNIT = {'天': 1, '日': 1, '周': 7, '星期': 7, '月': 30, '个月': 30, '年': 365}


def days(s):
    for a in '\u2014－~～至到':
        s = (s or '').replace(a, '-')
    m = re.search(r'([\d.]+)\s*(?:-\s*([\d.]+))?\s*(个月|天|日|周|星期|月|年)', s)
    if not m:
        return None
    try:
        return round(float(m.group(2) or m.group(1)) * UNIT[m.group(3)], 1)
    except ValueError:
        return None


def cost(s):
    s = (s or '').replace('\u2014\u2014', '-')
    for a, b in [('\u2014', '-'), ('－', '-'), ('~', '-'), (',', ''), ('，', '')]:
        s = s.replace(a, b)
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*元', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'(\d+)\s*元', s)
    return (float(m.group(1)), float(m.group(1))) if m else (None, None)


def clean(x):
    return (x or '').strip().replace('\r', ' ')


def text(x):
    return clean(x) or None


CN = {'recommand_eat': '推荐食谱', 'no_eat': '忌吃', 'do_eat': '宜吃', 'belongs_to': '所属科室', 'common_drug': '常用药品',
      'drugs_of': '生产药品', 'recommand_drug': '好评药品', 'need_check': '诊断检查', 'has_symptom': '症状', 'acompany_with': '并发症'}
ENDS = {'recommand_eat': ('Disease', 'Food'), 'no_eat': ('Disease', 'Food'), 'do_eat': ('Disease', 'Food'),
        'common_drug': ('Disease', 'Drug'), 'recommand_drug': ('Disease', 'Drug'), 'need_check': ('Disease', 'Check'),
        'has_symptom': ('Disease', 'Symptom'), 'acompany_with': ('Disease', 'Disease'), 'drugs_of': ('Producer', 'Drug'),
        'belongs_to_dd': ('Disease', 'Department'), 'belongs_to_pp': ('Department', 'Department')}

# ---------------------------------------------------------------- read medical.json
recs = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
disease = {}
pools = {lab: set() for lab in ['Drug', 'Food', 'Check', 'Department', 'Producer', 'Symptom']}
rels = {k: [] for k in ENDS}
for r in recs:
    n = clean(r['name'])
    if not n or n in disease:
        continue
    lo, hi = cost(r.get('cost_money'))
    disease[n] = dict(name=n, description=text(r.get('desc')), cause=text(r.get('cause')), prevent=text(r.get('prevent')),
                      category=text('、'.join(r.get('category') or [])), easy_get=text(r.get('easy_get')),
                      get_way=text(r.get('get_way')), yibao_status=text(r.get('yibao_status')),
                      get_prob=text(r.get('get_prob')), cured_prob=text(r.get('cured_prob')),
                      cure_lasttime=text(r.get('cure_lasttime')), cost_money=text(r.get('cost_money')),
                      cure_way=text('、'.join(r.get('cure_way') or [])),
                      cure_department=text('、'.join(r.get('cure_department') or [])),
                      get_prob_pct=pct(r.get('get_prob')), cured_prob_pct=pct(r.get('cured_prob')),
                      cure_days=days(r.get('cure_lasttime')), cost_min=lo, cost_max=hi)
    for key, lab, rel in [('symptom', 'Symptom', 'has_symptom'), ('check', 'Check', 'need_check'),
                          ('common_drug', 'Drug', 'common_drug'), ('recommand_drug', 'Drug', 'recommand_drug'),
                          ('do_eat', 'Food', 'do_eat'), ('not_eat', 'Food', 'no_eat'), ('recommand_eat', 'Food', 'recommand_eat')]:
        for i, x in enumerate(r.get(key) or []):
            x = clean(x)
            if x:
                pools[lab].add(x)
                rels[rel].append((n, x, i + 1))
    for i, x in enumerate(r.get('acompany') or []):
        if clean(x):
            rels['acompany_with'].append((n, clean(x), i + 1))
    cd = [clean(x) for x in (r.get('cure_department') or []) if clean(x)]
    pools['Department'].update(cd)
    if len(cd) == 1:
        rels['belongs_to_dd'].append((n, cd[0], None))
    elif len(cd) == 2:
        rels['belongs_to_pp'].append((cd[1], cd[0], None))
        rels['belongs_to_dd'].append((n, cd[1], None))
    for x in r.get('drug_detail') or []:
        x = clean(x)
        if '(' in x:
            p, d = x.split('(')[0].strip(), x.split('(')[-1].replace(')', '').strip()
            if p and d:
                pools['Producer'].add(p)
                pools['Drug'].add(d)
                rels['drugs_of'].append((p, d, None))
rels['acompany_with'] = [t for t in rels['acompany_with'] if t[1] in disease]   # complications must be diseases
for k in rels:                                                                    # one edge per (start, end), first rank
    seen, out = set(), []
    for s, d, rk in rels[k]:
        if (s, d) not in seen:
            seen.add((s, d))
            out.append((s, d, rk))
    rels[k] = out
rels['belongs_to_pp'] = [t for t in rels['belongs_to_pp'] if t[0] != t[1]]

# ---------------------------------------------------------------- load into Neo4j
t0 = time.time()
with session(write=True) as s:
    if s.run('MATCH (n) RETURN count(n) AS c').single()['c'] > 0:
        sys.exit('The database is not empty. Drop it and create it again (guide step 2a), then rerun.')
    for lab in ['Disease'] + list(pools):
        s.run(f'CREATE CONSTRAINT {lab.lower()}_name IF NOT EXISTS FOR (n:{lab}) REQUIRE n.name IS UNIQUE').consume()

    def batches(rows, n=5000):
        for i in range(0, len(rows), n):
            yield rows[i:i + n]
    for b in batches(list(disease.values())):
        s.run('UNWIND $rows AS r CREATE (d:Disease) SET d = r', rows=b).consume()
    for lab, names in pools.items():
        for b in batches(sorted(names)):
            s.run(f'UNWIND $rows AS x CREATE (:{lab} {{name: x}})', rows=b).consume()
    for k, (a, b_) in ENDS.items():
        typ = 'belongs_to' if k.startswith('belongs_to') else k
        rows = [dict(s=x, d=y, rank=rk) for x, y, rk in rels[k]]
        for b in batches(rows):
            s.run(f'UNWIND $rows AS r MATCH (a:{a} {{name: r.s}}), (b:{b_} {{name: r.d}}) '
                  f'CREATE (a)-[e:{typ} {{name: $cn}}]->(b) SET e.rank = r.rank', rows=b, cn=CN[typ]).consume()
    stats = {'nodes': {}, 'edges': {}}
    for lab in ['Disease'] + list(pools):
        stats['nodes'][lab] = s.run(f'MATCH (n:{lab}) RETURN count(n) AS c').single()['c']
    for typ in sorted({k if not k.startswith('belongs_to') else 'belongs_to' for k in ENDS}):
        stats['edges'][typ] = s.run(f'MATCH ()-[e:{typ}]->() RETURN count(e) AS c').single()['c']
    stats['numeric_coverage'] = {c: s.run(f'MATCH (d:Disease) WHERE d.{c} IS NOT NULL RETURN count(d) AS c').single()['c']
                                 for c in ['get_prob_pct', 'cured_prob_pct', 'cure_days', 'cost_min', 'cost_max']}
stats['n_nodes'] = sum(stats['nodes'].values())
stats['n_edges'] = sum(stats['edges'].values())
stats['seconds'] = round(time.time() - t0)
json.dump(stats, open(work('logs', 'kg_stats.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(stats, ensure_ascii=False, indent=1))
print('OK' if (stats['n_nodes'], stats['n_edges']) == (44108, 291083) else 'COUNTS DIFFER from 44108 nodes / 291083 edges')
