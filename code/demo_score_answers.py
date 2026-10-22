# demo_score_answers.py - score a small set of answers "Qxx: <Cypher>" against gold queries, showing EM and EX step
# by step: the clause sets that EM compares and the result rows that EX compares. Default: the 8 Đái tháo đường
# (diabetes) questions of demo/diabetes8_prompt.txt and the ChatGPT answers of demo/diabetes8_chatgpt_web.txt.
# Output: work/scores/ask/<answers file name>_<YYYYMMDD_HHMM>.json (EM, EX total and per question).
# Usage (from the folder that contains code/ and work/; needs the Neo4j password for EX):
#   python code/demo_score_answers.py                                   demo/diabetes8_chatgpt_web.txt (chatgpt.com answers)
#   python code/demo_score_answers.py work/chatgpt_web_demo/my_answers.txt   any file with lines "Qxx: <Cypher>"
import getpass
import json
import os
import time
import re
import sys

os.environ.setdefault('NL2GQL_LANG', 'vi')
if not os.environ.get('NEO4J_PASSWORD'):
    os.environ['NEO4J_PASSWORD'] = getpass.getpass('Neo4j DBMS password (not echoed): ')
sys.path.insert(0, 'code')
from common import run  # noqa: E402
from metrics import em_components, exact_match, exec_match, gold_rows  # noqa: E402

D = 'Đái tháo đường'
GOLD = {
    'Q01': ('xét nghiệm', f"MATCH (d:Disease{{name:'{D}'}})-[:need_check]->(c:Check) RETURN c.name"),
    'Q02': ('thuốc thường dùng', f"MATCH (d:Disease{{name:'{D}'}})-[:common_drug]->(g:Drug) RETURN g.name"),
    'Q03': ('kiêng ăn', f"MATCH (d:Disease{{name:'{D}'}})-[:no_eat]->(f:Food) RETURN f.name"),
    'Q04': ('chi phí cao nhất', f"MATCH (d:Disease{{name:'{D}'}}) RETURN d.cost_max"),
    'Q05': ('triệu chứng xếp đầu', f"MATCH (d:Disease{{name:'{D}'}})-[r:has_symptom]->(s:Symptom) WHERE r.rank = 1 RETURN s.name"),
    'Q06': ('có biến chứng Tăng huyết áp', f"MATCH (d:Disease{{name:'{D}'}}) OPTIONAL MATCH (d)-[:acompany_with]->"
                                           "(d2:Disease{name:'Tăng huyết áp'}) RETURN count(d2) > 0"),
    'Q07': ('metformin và Uống nhiều', "MATCH (g:Drug{name:'Viên nén metformin hydroclorid'})<-[:common_drug]-(d:Disease)"
                                       "-[:has_symptom]->(s:Symptom{name:'Uống nhiều'}) RETURN d.name"),
    'Q08': ('tiểu đường (tên thường gọi)', f"MATCH (d:Disease{{name:'{D}'}})-[:need_check]->(c:Check) RETURN c.name"),
}
path = sys.argv[1] if len(sys.argv) > 1 else 'demo/diabetes8_chatgpt_web.txt'
ans = {}
for line in open(path, encoding='utf-8'):
    m = re.match(r'\s*(Q\d+)\s*:\s*(.+)', line)
    if m:
        ans[m.group(1)] = m.group(2).strip()
LINE = '=' * 100


def rows(q):
    try:
        return [list(r) for r in run(q)[1]]
    except Exception as e:
        return f'lỗi: {str(e).splitlines()[0][:100]}'


try:                                                          # wrong password or Neo4j not started: say so plainly
    run('RETURN 1')
except Exception as e:
    sys.exit(f'DỪNG: không nối được Neo4j ({str(e).splitlines()[0][:120]}). Kiểm Neo4j Desktop đã Start, '
             'CSDL diseasekg-vi, và gõ đúng mật khẩu.')
em_n = ex_n = 0
items = []
for q, (topic, gold) in GOLD.items():
    pred = ans.get(q, '')
    if not gold_rows(gold):                                   # a gold query with no rows means the wrong database
        sys.exit(f"DỪNG: câu đúng {q} ra 0 dòng. Kiểm CSDL đang nối (NEO4J_DB={os.environ.get('NEO4J_DB', 'mặc định')}), "
                 "phải là diseasekg-vi và Neo4j đã Start.")
    em, ex = exact_match(pred, gold), exec_match(pred, gold_rows(gold))
    em_n, ex_n = em_n + em, ex_n + ex
    items.append(dict(id=q, topic=topic, gold=gold, pred=pred, em=em, ex=ex))
    print(LINE)
    print(f'{q} ({topic})')
    print('  đúng   :', gold)
    print('  trả lời:', pred)
    print('  EM so mệnh đề (biến đổi tên v0, v1...):')
    for name, x in (('đúng', gold), ('trả lời', pred)):
        print(f'    {name}:', '  '.join(f'{k} {sorted(p for p, _ in el)}' for k, el in em_components(x)))
    g, p = rows(gold), rows(pred)
    print(f'  EX so kết quả: đúng {len(g)} dòng {g[:4]}', '...' if len(g) > 4 else '')
    print(f'                 trả lời {len(p) if isinstance(p, list) else 0} dòng {p if isinstance(p, str) else p[:4]}')
    print(f'  ==> EM = {em}   EX = {ex}')
print(LINE)
n = len(GOLD)
print(f'Tổng {n} câu: EM {em_n}/{n} = {100 * em_n / n:.2f}%   EX {ex_n}/{n} = {100 * ex_n / n:.2f}%   ({path})')
os.makedirs('work/scores/ask', exist_ok=True)                 # keep the scores, not only the screen output
out = f"work/scores/ask/{os.path.basename(path).rsplit('.', 1)[0]}_{time.strftime('%Y%m%d_%H%M')}.json"
json.dump(dict(answers=path, n=n, EM=round(100 * em_n / n, 2), EX=round(100 * ex_n / n, 2), items=items),
          open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('saved', out)
