# run_steps.py - run several steps of the guide with the Neo4j password typed once (it is passed to the child processes
# only, never written to disk). Stops at the first failing step; full output goes to work/logs/run_steps_<group>.log.
# Usage (from the folder that contains code/ and work/; NL2GQL_LANG and NEO4J_DB are taken from the environment):
#   python code/run_steps.py data       step 3c-3f (both rounds, ChatGPT via code/gpt_api.py), step 4, step 5
#   python code/run_steps.py score      step 7: gold sanity check, then EM/EX of work/out/random/preds
#   python code/run_steps.py chatgpt    step 9: 50-question sheet, ChatGPT answers via API, EM/EX
#   python code/run_steps.py synonym    synonym normalization test (code/synonym_test.py)
import getpass
import os
import subprocess
import sys
import time

group = sys.argv[1] if len(sys.argv) > 1 else 'data'
user = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('KAGGLE_USER', 'vanthieu')
py = sys.executable
GROUPS = {
    'data': [
        ('3c round 1: check replies', [py, 'code/collect.py', '--round', '1']),
        ('3d round 1: CoT via API', [py, 'code/gpt_api.py', '--cot', '1']),
        ('3e round 1: keep similarity >= 0.8', [py, 'code/cot_check.py', '--round', '1']),
        ('3a round 2: prompts', [py, 'code/gen_prompts.py', '--round', '2']),
        ('3b round 2: templates via API', [py, 'code/gpt_api.py', '--round', '2']),
        ('3c round 2: check replies', [py, 'code/collect.py', '--round', '2']),
        ('3d round 2: CoT via API', [py, 'code/gpt_api.py', '--cot', '2']),
        ('3e round 2: keep similarity >= 0.8', [py, 'code/cot_check.py', '--round', '2']),
        ('3f: grounding, 7:1:2 split', [py, 'code/ground_split.py']),
        ('4: relevant schema', [py, 'code/build_contexts.py']),
        ('5: Kaggle package', [py, 'code/kaggle_pack.py', '--user', user]),
    ],
    'score': [
        ('7: gold vs gold (must be 100/100)', [py, 'code/score.py', '--gold-sanity']),
        ('7: EM and EX of the Kaggle predictions', [py, 'code/score.py', '--preds', 'work/out/random/preds']),
    ],
    'chatgpt': [
        ('9a: 50-question sheet', [py, 'code/chatgpt_sheet.py']),
        ('9b: ChatGPT answers via API', [py, 'code/gpt_api.py', '--prompt-file', 'work/chatgpt_50questions/prompt_chatgpt.txt',
                                         '--out-file', 'work/chatgpt_50questions/answers_chatgpt.txt']),
        ('9c: EM and EX of ChatGPT', [py, 'code/score.py', '--chatgpt', 'work/chatgpt_50questions/answers_chatgpt.txt']),
    ],
    'synonym': [
        ('synonym test: entity linking', [py, 'code/synonym_test.py', 'link']),
        ('synonym test: EX before/after', [py, 'code/synonym_test.py', 'ex']),
    ],
}
if group not in GROUPS:
    sys.exit('group must be one of: ' + ', '.join(GROUPS))
env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
env['NEO4J_PASSWORD'] = getpass.getpass('Neo4j DBMS password (not echoed): ')

# Check the database first: a run started while the DBMS was still booting rejects every reply as invalid Cypher.
check = ("import sys; sys.path.insert(0, 'code'); from common import session\n"
         "with session() as s: n = s.run('MATCH (n) RETURN count(n) AS n').single()['n']\n"
         "print('Neo4j OK, nodes:', n); sys.exit(0 if n > 40000 else 1)")
for i in range(10):
    p = subprocess.run([py, '-c', check], env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if p.returncode == 0:
        print(p.stdout.strip())
        break
    print('Neo4j not reachable yet (start the DBMS in Neo4j Desktop); retrying in 15 s')
    time.sleep(15)
else:
    sys.exit('STOP: Neo4j not reachable or wrong password.\n' + (p.stdout + p.stderr)[-600:])

os.makedirs('work/logs', exist_ok=True)
log = open(f'work/logs/run_steps_{group}.log', 'a', encoding='utf-8')
for name, cmd in GROUPS[group]:
    t0 = time.time()
    print(f'\n=== {name}', flush=True)
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    out = (p.stdout or '') + (p.stderr or '')
    log.write(f'\n=== {time.strftime("%Y-%m-%d %H:%M")} {name}\n{out}')
    log.flush()
    print('\n'.join(out.strip().splitlines()[-12:]))
    print(f'--- {time.time() - t0:.0f} s', flush=True)
    if p.returncode != 0:
        sys.exit(f'STOP at "{name}" (code {p.returncode}); see work/logs/run_steps_{group}.log')
print(f'\nDONE: {group}')
