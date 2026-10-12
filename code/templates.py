# templates.py - NL-GQL template pairs: question types, slot rules, checks of ChatGPT's pairs, and grounding
# (filling the slots [d], [s], ... with real names from Neo4j). Used by gen_prompts.py, collect.py and ground_split.py.
# Slot convention: an entity appears in the GQL only as (var:Label{name:'[slot]'}); [m] is a number, [str] a substring.
import collections
import json
import os
import re

from common import run, explain_ok
from schema import NODES, EDGES

TYPE_DESC = {
    1: '实体属性：询问某个实体的一个或多个属性，例如\u201c[d]的病因是什么？\u201d',
    2: '数值排序：按数值属性或数量排序后取前几个，例如\u201c[k]科室中治愈率最高的[m]种疾病是什么？\u201d',
    3: '关系推理：沿一条或多条关系找到相关实体，例如\u201c出现[s]症状的疾病常用哪些药？\u201d',
    4: '是非问题：回答是或否，例如\u201c[d]的治愈率是否高于[m]%？\u201d',
    5: '关系过滤：同时满足两个关系条件的实体，例如\u201c既要做[c]检查又忌吃[f]的疾病有哪些？\u201d',
    6: '属性比较：比较两个实体的属性或求差值，例如\u201c[d1]和[d2]的最高治疗费用相差多少元？\u201d',
    7: '边属性：利用关系上的属性（rank，在原始列表中的位次）过滤或返回，例如\u201c[d]的第1个症状是什么？\u201d',
    8: '字符串过滤：名称或文本包含、以某字符串开头或结尾，例如\u201c名称包含\u201c[str]\u201d的食物有哪些？\u201d',
}
SLOT_LABEL = {'d': 'Disease', 's': 'Symptom', 'c': 'Check', 'g': 'Drug', 'f': 'Food', 'k': 'Department', 'p': 'Producer'}
SLOT_RULES = ("槽位约定：实体只能以 (变量:标签{name:'[槽位]'}) 的形式出现在 GQL 中。"
              "[d] [d1] [d2] 表示疾病，[s] [s1] [s2] 症状，[c] [c1] [c2] 检查项目，[g] [g1] [g2] 药品，"
              "[f] [f1] [f2] 食物，[k] 科室，[p] 生产厂商，[m] 数字，[str] 子字符串。"
              "自然语言问题中必须出现与 GQL 完全相同的槽位，不能多也不能少。")
TYPE_DESC_VI = {
    1: 'Thuộc tính thực thể: hỏi một hay nhiều thuộc tính của một thực thể, ví dụ “Nguyên nhân của [d] là gì?”',
    2: 'Sắp xếp số: sắp theo thuộc tính số hoặc số lượng rồi lấy vài kết quả đầu, ví dụ “[m] bệnh có tỉ lệ chữa khỏi cao nhất thuộc [k] là những bệnh nào?”',
    3: 'Suy luận quan hệ: đi theo một hay nhiều quan hệ để tìm thực thể liên quan, ví dụ “Các bệnh có triệu chứng [s] thường dùng thuốc gì?”',
    4: 'Câu hỏi có/không: trả lời có hoặc không, ví dụ “Tỉ lệ chữa khỏi của [d] có cao hơn [m]% không?”',
    5: 'Lọc theo quan hệ: thực thể thoả cùng lúc hai điều kiện quan hệ, ví dụ “Những bệnh nào vừa cần xét nghiệm [c] vừa phải kiêng ăn [f]?”',
    6: 'So sánh thuộc tính: so sánh hoặc tính chênh lệch thuộc tính của hai thực thể, ví dụ “Chi phí điều trị cao nhất của [d1] và [d2] chênh nhau bao nhiêu tệ?”',
    7: 'Thuộc tính cạnh: dùng thuộc tính trên quan hệ (rank, vị trí trong danh sách gốc) để lọc hoặc trả về, ví dụ “Triệu chứng đứng đầu của [d] là gì?”',
    8: 'Lọc chuỗi: tên hoặc văn bản chứa, bắt đầu hay kết thúc bằng một chuỗi, ví dụ “Những thực phẩm nào có tên chứa [str]?”',
}
SLOT_RULES_VI = ("Quy ước chỗ trống: thực thể chỉ được xuất hiện trong GQL dưới dạng (biến:Nhãn{name:'[chỗ trống]'}). "
                 "[d] [d1] [d2] là bệnh, [s] [s1] [s2] triệu chứng, [c] [c1] [c2] xét nghiệm, [g] [g1] [g2] thuốc, "
                 "[f] [f1] [f2] thực phẩm, [k] khoa, [p] hãng sản xuất, [m] một con số, [str] một chuỗi con. "
                 "Câu hỏi tiếng Việt phải có đúng các chỗ trống như trong GQL, không thừa không thiếu.")
if os.environ.get('NL2GQL_LANG', 'zh') == 'vi':
    TYPE_DESC, SLOT_RULES = TYPE_DESC_VI, SLOT_RULES_VI
LABELS = set(NODES)
EDGE_ENDS = {e[0]: set() for e in EDGES}
for name, s, d, _, _ in EDGES:
    EDGE_ENDS[name].add((s, d))
NODE_PROPS = {lab: {p for p, _, _ in ps} for lab, ps in NODES.items()}
EDGE_PROPS = {'name', 'rank'}


def parse_json_lines(text):
    """Pull every JSON object out of a ChatGPT reply (one object per line, code fences allowed)."""
    out = []
    for line in text.replace('```json', '').replace('```', '').splitlines():
        line = line.strip().rstrip(',')
        if not line.startswith('{'):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ------------------------------------------------------------------ template checks
KW = re.compile(r'\b(OPTIONAL MATCH|MATCH|WHERE|WITH|RETURN|ORDER BY|LIMIT)\b')


def clauses(g):
    pos = [(m.start(), m.group(1)) for m in KW.finditer(g)]
    out = []
    for i, (st, k) in enumerate(pos):
        en = pos[i + 1][0] if i + 1 < len(pos) else len(g)
        out.append((k, g[st + len(k):en].strip()))
    return out


def schema_problems(nl, g, kw):
    """Format and schema checks of one NL-GQL template pair; returns a list of problems."""
    probs = []
    if not g.strip().upper().startswith(('MATCH', 'OPTIONAL MATCH')):
        probs.append('GQL must start with MATCH')
    if re.search(r'\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL|LOAD)\b', g, flags=re.I):
        probs.append('write or procedure clause')
    vl = dict(re.findall(r'\((\w+):(\w+)', g))
    for v, lab in vl.items():
        if lab not in LABELS:
            probs.append(f'unknown label {lab}')
    for r in re.findall(r'\[\w*:(\w+)', g):
        if r not in EDGE_ENDS:
            probs.append(f'unknown relationship {r}')
    rel_vars = set(re.findall(r'\[(\w+):\w+', g))
    for v, p in re.findall(r'\b(\w+)\.(\w+)\b', g):
        if v in vl and vl[v] in NODE_PROPS and p not in NODE_PROPS[vl[v]]:
            probs.append(f'unknown property {vl[v]}.{p}')
        if v in rel_vars and p not in EDGE_PROPS:
            probs.append(f'unknown relationship property {p}')
    for v, lab, s in re.findall(r"\((\w+):(\w+)\{name:'\[(\w+)\]'\}\)", g):
        if s[0] not in SLOT_LABEL or SLOT_LABEL[s[0]] != lab:
            probs.append(f'slot [{s}] does not match label {lab}')
    slots_g = set(re.findall(r"'\[(\w+)\]'", g)) | set(re.findall(r'\[(m|str)\]', g))
    slots_nl = set(re.findall(r'\[(\w+)\]', nl))
    if slots_nl != slots_g:
        probs.append(f'slot mismatch NL{sorted(slots_nl)} GQL{sorted(slots_g)}')
    if 'm' in slots_g and not kw.get('m'):
        probs.append('[m] used but no numbers given in "m"')
    if 'str' in slots_g and not kw.get('str'):
        probs.append('[str] used but no strings given in "str"')
    return probs


def explain_template(g, kw):
    """EXPLAIN the template with placeholder values filled in."""
    q = re.sub(r"'\[(\w+)\]'", "'x'", g)
    q = q.replace('[m]', str((kw.get('m') or [1])[0])).replace("'[str]'", "'x'").replace('[str]', 'x')
    return explain_ok(q)


# ------------------------------------------------------------------ grounding (deterministic: ORDER BY everywhere)
def split_top(s, sep=','):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if ch == sep and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def binding_groups(g):
    paths = []
    for k, body in clauses(g):
        if k in ('MATCH', 'OPTIONAL MATCH'):
            for p in split_top(body):
                slots = dict((v, s) for v, l, s in re.findall(r"\((\w+):(\w+)\{name:'\[(\w+)\]'\}\)", p))
                stripped = re.sub(r"\{name:'\[\w+\]'\}", '', p)
                vs = set(re.findall(r'\((\w+)', p))
                paths.append((stripped, vs, slots))
    parent = list(range(len(paths)))

    def f(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i in range(len(paths)):
        for j in range(i):
            if paths[i][1] & paths[j][1]:
                parent[f(i)] = f(j)
    groups = collections.defaultdict(list)
    for i, p in enumerate(paths):
        groups[f(i)].append(p)
    out = []
    for gp in groups.values():
        slots = {}
        for _, _, s in gp:
            slots.update(s)
        if slots:
            out.append(([p[0] for p in gp], slots))
    return out


_pool = {}


def entity_pool(lab):
    if lab not in _pool:
        _, rows = run(f'MATCH (n:{lab}) RETURN n.name ORDER BY n.name')
        _pool[lab] = [x[0] for x in rows if x[0] and "'" not in x[0] and '\\' not in x[0] and len(x[0]) <= 30]
    return _pool[lab]


def bind_group(paths, slots, rng, tries=40):
    vars_ = list(slots)
    anchor = vars_[0]
    lab = SLOT_LABEL[slots[anchor][0]]
    for _ in range(tries):
        val = rng.choice(entity_pool(lab))
        conds = [f"{anchor}.name = '{val}'"]
        for i, a in enumerate(vars_):
            for b in vars_[:i]:
                if SLOT_LABEL[slots[a][0]] == SLOT_LABEL[slots[b][0]]:
                    conds.append(f'{a}.name <> {b}.name')
        ret = ', '.join(v + '.name' for v in vars_)
        q = f"MATCH {', '.join(paths)} WHERE {' AND '.join(conds)} RETURN DISTINCT {ret} ORDER BY {ret} LIMIT 300"
        try:
            _, rows = run(q)
        except Exception:
            return None
        rows = [r for r in rows if all(x and "'" not in x and '\\' not in x for x in r)]
        if rows:
            r = rng.choice(rows)
            return {slots[v]: r[i] for i, v in enumerate(vars_)}
    return None


def fill(text, b):
    for k, v in b.items():
        text = text.replace(f'[{k}]', str(v))
    return text


def fmt_num(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def nonempty(rows):
    return any(any(v not in (None, '', []) for v in r) for r in rows)


def tie_safe(gql):
    m = re.search(r'RETURN (.*) ORDER BY (\S+) (ASC|DESC) LIMIT (\d+)\s*$', gql)
    if not m:
        return True
    proj, key, dr, k = m.group(1), m.group(2), m.group(3), int(m.group(4))
    items = split_top(proj)
    aliases = [re.split(r'\s+AS\s+', it)[-1].strip() if ' AS ' in it else it.strip() for it in items]
    if key in aliases:
        q = gql[:m.start()] + f'RETURN {proj} ORDER BY {key} {dr}'
        idx = aliases.index(key)
    else:
        q = gql[:m.start()] + f'RETURN {proj}, {key} AS __sk ORDER BY {key} {dr}'
        idx = len(items)
    try:
        _, rows = run(q)
    except Exception:
        return False
    if len(rows) <= k:
        return True
    bk = rows[k - 1][idx]
    if rows[k][idx] != bk:
        return True
    return len({tuple(r[:len(items)]) for r in rows if r[idx] == bk}) == 1


def norm_answer(rows):
    return [[(round(v, 4) if isinstance(v, float) else v) for v in r] for r in rows]

