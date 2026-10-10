# common.py - paths, Neo4j connection and small helpers shared by every script.
# <ROOT> is the folder that contains code/ (for example D:/Labs/nl2gql); every result is written under <ROOT>/work.
# Neo4j connection from environment variables: NEO4J_URI (default bolt://localhost:7687 = Neo4j Desktop),
# NEO4J_DB (default diseasekg), NEO4J_USER (default neo4j), NEO4J_PASSWORD (your DBMS password).
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace(chr(92), '/')
WORK = ROOT + '/work'
SEED = 20261010
TYPE_NAME = {1: 'Entity property', 2: 'Numerical sorting', 3: 'Relationship inference', 4: 'Yes/No question',
             5: 'Relationship filtering', 6: 'Attribute comparison', 7: 'Edge property', 8: 'String filtering'}


def work(*parts):
    """Path under <ROOT>/work; parent folders are created."""
    p = '/'.join([WORK] + [str(x) for x in parts])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def read_jsonl(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]


def write_jsonl(p, rows):
    with open(p, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def rng_for(*tags):
    """Random generator seeded by a fixed string, so every run makes the same choices."""
    return random.Random(f'{SEED}-' + '-'.join(map(str, tags)))


_driver = None


def driver():
    global _driver
    import neo4j
    if _driver is None:
        pw = os.environ.get('NEO4J_PASSWORD')
        auth = (os.environ.get('NEO4J_USER', 'neo4j'), pw) if pw else None
        _driver = neo4j.GraphDatabase.driver(os.environ.get('NEO4J_URI', 'bolt://localhost:7687'), auth=auth,
                                             notifications_min_severity='OFF')
    return _driver


def session(write=False):
    import neo4j
    return driver().session(database=os.environ.get('NEO4J_DB', 'diseasekg'),
                            default_access_mode=neo4j.WRITE_ACCESS if write else neo4j.READ_ACCESS)


def plain(v):
    """Nodes and relationships in a result are compared by their properties."""
    import neo4j.graph
    if isinstance(v, (neo4j.graph.Node, neo4j.graph.Relationship)):
        return dict(v.items())
    if isinstance(v, list):
        return [plain(x) for x in v]
    return v


def run(q, timeout=15, max_rows=100000):
    """Run one read-only Cypher query; returns (column names, rows). Raises on syntax error or timeout."""
    import neo4j
    with session() as s:
        res = s.run(neo4j.Query(q, timeout=timeout))
        cols, rows = list(res.keys()), []
        for rec in res:
            rows.append([plain(x) for x in rec.values()])
            if len(rows) >= max_rows:
                break
    return cols, rows


def explain_ok(q):
    """Syntax and schema check by Neo4j without running the query (EXPLAIN)."""
    try:
        run('EXPLAIN ' + q)
        return True, ''
    except Exception as e:
        return False, str(e).split('\n')[0][:200]
