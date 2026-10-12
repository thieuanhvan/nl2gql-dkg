# metrics.py - EM and EX (paper Sec. 5.1, as in Spider) and the relevant-schema extractor (paper Sec. 4.3).
# EM: split the query into clauses (MATCH, WHERE, RETURN, ...), rename variables by order of appearance, and compare
#     the SET of parts inside each clause (order of AND conditions or RETURN items does not matter).
# EX: run predicted and gold query on Neo4j and compare the multiset of result rows (column names and row order ignored).
# Extractor: label linker (longest dictionary match of entity names in the question; ties broken by the most similar
#     training question) + trigger words + join-table linker (A* shortest paths on the schema graph).
import collections
import heapq
import json
import math
import re

from common import LANG, run
from schema import NODES, EDGES, EDGE_TRIGGERS, PROP_TRIGGERS, LABEL_TRIGGERS, render_schema

# ============================================================== EM
CLAUSE_RE = re.compile(r'\b(OPTIONAL MATCH|MATCH|WHERE|WITH|RETURN|ORDER BY|SKIP|LIMIT|UNWIND|UNION)\b', re.I)

def _strip(q):
    q = (q or '').strip()
    m = re.search(r'```(?:cypher|sql|gql)?\s*(.*?)```', q, re.S | re.I)
    if m:
        q = m.group(1)
    q = q.strip().rstrip(';').replace('"', "'").replace('`', '')
    q = re.sub(r'\s+', ' ', q)
    return q

def _split_top(s, sep=','):
    out, depth, cur, inq = [], 0, '', False
    for ch in s:
        if ch == "'":
            inq = not inq
        if not inq:
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
        if ch == sep and depth == 0 and not inq:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out

def _canon_vars(q):
    """Rename pattern/alias variables by first appearance (v0, v1, ...) so that EM is not sensitive to
    variable naming; string literals are protected."""
    lits = []
    def keep(m):
        lits.append(m.group(0)); return f'\x00{len(lits) - 1}\x00'
    q = re.sub(r"'[^']*'", keep, q)
    names = []
    for m in re.finditer(r'[(\[]\s*(\w+)\s*[:)\]{]|\bAS\s+(\w+)', q, re.I):
        v = m.group(1) or m.group(2)
        if v and v not in names and not v.upper() in ('AS',):
            names.append(v)
    mp = {v: f'v{i}' for i, v in enumerate(names)}
    if mp:
        q = re.sub(r'\b(' + '|'.join(map(re.escape, sorted(mp, key=len, reverse=True))) + r')\b(?!\s*:\s*\w+\s*[,}])',
                   lambda m: mp[m.group(1)], q)
    return re.sub(r'\x00(\d+)\x00', lambda m: lits[int(m.group(1))], q)

def _norm_body(b):
    b = re.sub(r'\s*([(){}\[\],:<>=+\-*/])\s*', r'\1', b.strip())
    b = re.sub(r'\b(as|and|or|not|xor|is|in|asc|desc|distinct|contains|starts|ends|with|true|false|null|count|avg|sum|min|max|abs|collect|exists)\b',
               lambda m: m.group(1).upper(), b, flags=re.I)
    return b

def em_components(q):
    q = _canon_vars(_strip(q))
    pos = [(m.start(), m.group(1).upper()) for m in CLAUSE_RE.finditer(q)]
    comps = []
    for i, (st, k) in enumerate(pos):
        en = pos[i + 1][0] if i + 1 < len(pos) else len(q)
        body = q[st + len(k):en]
        if k in ('RETURN', 'WITH', 'ORDER BY', 'MATCH', 'OPTIONAL MATCH'):
            el = frozenset(collections.Counter(_norm_body(x) for x in _split_top(body)).items())
        elif k == 'WHERE':
            el = frozenset(collections.Counter(_norm_body(x) for x in re.split(r'\bAND\b', body, flags=re.I)).items())
        else:
            el = frozenset([(_norm_body(body), 1)])
        comps.append((k, el))
    return comps

def exact_match(pred, gold):
    try:
        return int(em_components(pred) == em_components(gold) and len(em_components(gold)) > 0)
    except Exception:
        return 0

# ============================================================== EX
def _norm_val(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float):
        if math.isnan(v):
            return 'nan'
        return round(v, 4) if not float(v).is_integer() else int(v)
    if isinstance(v, (list, tuple)):
        return tuple(_norm_val(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    return v

def gold_rows(gql):
    return [tuple(_norm_val(x) for x in r) for r in run(_strip(gql))[1]]


def exec_match(pred, gold):
    """EX = 1 if the prediction returns the same multiset of rows as the gold rows; errors and timeouts give 0."""
    try:
        rows = [tuple(_norm_val(x) for x in r) for r in run(_strip(pred))[1]]
    except Exception:
        return 0
    return int(collections.Counter(map(repr, rows)) == collections.Counter(map(repr, gold)))


# ============================================================== relevant schema
LABELS = list(NODES)
EDGE_KEYS = [(e[0], e[1], e[2]) for e in EDGES]

def gold_items(gql):
    vl = dict(re.findall(r'\((\w+):(\w+)', gql))
    labels = set(vl.values())
    edges = set()
    rels = set(re.findall(r'\[\w*:(\w+)\]', gql))
    for e in EDGE_KEYS:
        if e[0] in rels and e[1] in labels and e[2] in labels:
            edges.add(e)
    if re.search(r'\[\w+\]', gql):  # untyped relation: all edges between the labels
        for e in EDGE_KEYS:
            if e[1] in labels and e[2] in labels:
                edges.add(e)
    return labels, edges

def _bigrams(s):
    s = re.sub(r'\s+', '', s)
    return collections.Counter(s[i:i + 2] for i in range(len(s) - 1))

class SchemaExtractor:
    """Label linker (dictionary string match over all DB entity names, longest match first; ambiguity
    resolved with the labels used by the GQL of the most similar training NL) + keyword linker (Chinese
    trigger words for relations/properties) + join-table linker (A* shortest paths on the schema graph
    connecting all identified labels)."""

    def __init__(self, name2labels, train_items):
        self.n2l = name2labels
        if LANG == 'vi':  # Vietnamese names are capitalised; match them in the question regardless of case
            low = collections.defaultdict(set)
            for n, labs in name2labels.items():
                low[n.lower()] |= set(labs)
            self.n2l = low
        self.maxlen = max(len(n) for n in name2labels)
        self.train = [(_bigrams(x['nl']), gold_items(x['gql'])[0]) for x in train_items]
        idf = collections.Counter()
        for bg, _ in self.train:
            idf.update(set(bg))
        N = len(self.train)
        self.idf = {k: math.log((N + 1) / (v + 1)) + 1 for k, v in idf.items()}
        self.adj = collections.defaultdict(list)
        for e in EDGE_KEYS:
            self.adj[e[1]].append((e[2], e))
            self.adj[e[2]].append((e[1], e))

    def _vec(self, bg):
        v = {k: c * self.idf.get(k, 1.0) for k, c in bg.items()}
        n = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return v, n

    def similar_labels(self, nl, k=5):
        v, n = self._vec(_bigrams(nl))
        sims = []
        for bg, labs in self.train:
            w, m = self._vec(bg)
            sims.append((sum(v[x] * w.get(x, 0) for x in v) / (n * m), labs))
        sims.sort(key=lambda x: -x[0])
        return [labs for _, labs in sims[:k]]

    def link_entities(self, nl):
        if LANG == 'vi':
            nl = nl.lower()
        found, i = [], 0
        while i < len(nl):
            hit = None
            for L in range(min(self.maxlen, len(nl) - i), 1, -1):  # names of >= 2 chars
                s = nl[i:i + L]
                if s in self.n2l:
                    hit = s; break
            if hit:
                found.append(hit); i += len(hit)
            else:
                i += 1
        return found

    def astar(self, src, targets):
        # A* over schema labels with unit edge cost; heuristic h=0 is admissible (schema graph is tiny)
        pq = [(0, src, [])]
        seen = set()
        while pq:
            g, u, path = heapq.heappop(pq)
            if u in targets:
                return path
            if u in seen:
                continue
            seen.add(u)
            for v, e in self.adj[u]:
                if v not in seen:
                    heapq.heappush(pq, (g + 1, v, path + [(e, v)]))
        return None

    def extract(self, nl):
        labels, edges, props = set(), set(), collections.defaultdict(set)
        sims = None
        for ent in self.link_entities(nl):
            cands = self.n2l[ent]
            if len(cands) > 1:
                sims = sims or self.similar_labels(nl)
                pick = None
                for labs in sims:
                    inter = [c for c in cands if c in labs]
                    if inter:
                        pick = inter; break
                cands = pick or cands
            labels.update(cands)
        for r, trig in EDGE_TRIGGERS.items():
            if any(t in nl.lower() for t in trig):
                for e in EDGE_KEYS:
                    if e[0] == r:
                        edges.add(e); labels.update([e[1], e[2]])
        for lab, trig in LABEL_TRIGGERS.items():
            if any(t in nl.lower() for t in trig):
                labels.add(lab)
        for p, trig in PROP_TRIGGERS.items():
            if any(t in nl.lower() for t in trig) and p != 'rank':
                labels.add('Disease')
        if not labels:
            labels.add('Disease')
        # join-table linker: connect every label to the growing tree with an A* shortest path
        labs = sorted(labels, key=lambda x: (x != 'Disease', x))
        tree = {labs[0]}
        for lab in labs[1:]:
            if lab in tree:
                continue
            path = self.astar(lab, tree)
            if path:
                for e, v in path:
                    edges.add(e); tree.add(v)
            tree.add(lab)
        labels |= tree
        # keep only edges whose endpoints are both selected
        edges = {e for e in edges if e[1] in labels and e[2] in labels}
        return labels, edges

def render_items(labels, edges, cn=True):
    return render_schema(nodes=labels, edges=edges, cn=cn)
