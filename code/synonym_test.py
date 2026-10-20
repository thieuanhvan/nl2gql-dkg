# synonym_test.py - group extension (not in the paper): normalize everyday disease names to graph node names before the
# label linker. 32 hand-written Vietnamese questions use 8 everyday names (code/aliases_vi.tsv); each has a gold query with
# the real node name. Vietnamese version only (NL2GQL_LANG=vi, data/names_vi.tsv).
# Usage (from the folder that contains code/, data/ and work/):
#   python code/synonym_test.py link   share of questions whose entity the label linker finds, before/after (no Neo4j)
#   python code/synonym_test.py ex     ChatGPT (code/gpt_api.py) writes Cypher from question + relevant schema, before/after;
#                                      EX on Neo4j (needs NEO4J_PASSWORD; run through code/run_steps.py synonym)
# Output: work/synonym/questions.jsonl, link_result.json, prompt_*.txt, answers_*.txt, ex_result.json
import collections
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, 'code')
os.environ.setdefault('NL2GQL_LANG', 'vi')
from metrics import SchemaExtractor, render_items  # noqa: E402

W = 'work/synonym'
REL = {'check': ('need_check', 'Check', 'c'), 'drug': ('common_drug', 'Drug', 'g'), 'food': ('no_eat', 'Food', 'f')}
TEMPL = {'check': ['Bệnh {a} cần làm những xét nghiệm nào?', 'Muốn biết có bị {a} không thì đi xét nghiệm gì?'],
         'drug': ['Người bị {a} thường dùng thuốc gì?'],
         'food': ['Bị {a} thì nên kiêng ăn gì?']}

aliases = [tuple(line.rstrip('\n').split('\t')) for line in open('code/aliases_vi.tsv', encoding='utf-8')
           if line.strip() and not line.startswith('#')]


def questions():
    qs = []
    for a, c, _ in aliases:
        for kind, tps in TEMPL.items():
            rel, lab, v = REL[kind]
            for tp in tps:
                qs.append(dict(id=f'syn{len(qs) + 1:02d}', alias=a, canonical=c, kind=kind, nl=tp.format(a=a),
                               gql=f"MATCH (d:Disease{{name:'{c}'}})-[:{rel}]->({v}:{lab}) RETURN {v}.name"))
    return qs


def normalize(nl):
    for a, c, _ in sorted(aliases, key=lambda x: -len(x[0])):     # longest alias first
        nl = re.sub(re.escape(a), c, nl, flags=re.I)
    return nl


def extractor():
    n2l = collections.defaultdict(set)                           # names from the translation table, no database needed
    for line in open('data/names_vi.tsv', encoding='utf-8'):
        p = line.rstrip('\n').split('\t')
        if not line.startswith('#') and len(p) == 3 and len(p[2]) >= 2:
            n2l[p[2]].add(p[0])
    train = []
    if os.path.exists('work/data/train.jsonl'):
        train = [json.loads(x) for x in open('work/data/train.jsonl', encoding='utf-8')]
    return SchemaExtractor(n2l, train)


qs = questions()
os.makedirs(W, exist_ok=True)
with open(f'{W}/questions.jsonl', 'w', encoding='utf-8') as f:
    for q in qs:
        f.write(json.dumps(q, ensure_ascii=False) + '\n')
ex = extractor()
mode = sys.argv[1] if len(sys.argv) > 1 else 'link'

if mode == 'link':
    before = sum(q['canonical'].lower() in ex.link_entities(q['nl']) for q in qs)
    after = sum(q['canonical'].lower() in ex.link_entities(normalize(q['nl'])) for q in qs)
    out = dict(n=len(qs), linked_before=before, linked_after=after)
    json.dump(out, open(f'{W}/link_result.json', 'w', encoding='utf-8'), indent=1)
    print(out)

if mode == 'ex':
    from metrics import exec_match, gold_rows  # noqa: E402
    head = ('Bạn là chuyên gia truy vấn CSDL đồ thị Neo4j (Cypher). Với mỗi câu hỏi dưới đây, viết đúng MỘT câu Cypher '
            'dựa trên phần schema liên quan đi kèm; tên thực thể ghi đúng như trong câu hỏi. Trả lời mỗi dòng đúng dạng '
            '"syn01: <Cypher>", không giải thích.\n\n')
    for tag, fn in (('before', lambda s: s), ('after', normalize)):
        body = []
        for q in qs:
            nl = fn(q['nl'])
            labels, edges = ex.extract(nl)
            body.append(f"{q['id']}: {nl}\n[Schema liên quan]\n{render_items(labels, edges, cn=True)}\n")
        open(f'{W}/prompt_{tag}.txt', 'w', encoding='utf-8').write(head + '\n'.join(body))
        subprocess.run([sys.executable, 'code/gpt_api.py', '--prompt-file', f'{W}/prompt_{tag}.txt',
                        '--out-file', f'{W}/answers_{tag}.txt'], check=True)
    result = {}
    for tag in ('before', 'after'):
        pred = {}
        text = open(f'{W}/answers_{tag}.txt', encoding='utf-8').read().replace('```cypher', '').replace('```', '')
        for line in text.splitlines():
            m = re.match(r'\s*(syn\d+)\s*:\s*(.+)', line)
            if m:
                pred[m.group(1)] = m.group(2).strip()
        ok = sum(1 for q in qs if q['id'] in pred and exec_match(pred[q['id']], gold_rows(q['gql'])))
        result[tag] = dict(ex_correct=ok, n=len(qs), answered=len(pred))
    json.dump(result, open(f'{W}/ex_result.json', 'w', encoding='utf-8'), indent=1)
    print(result)
