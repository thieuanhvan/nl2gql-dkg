# gpt_api.py - step 3 through the OpenAI API, as in the paper: send prompt files to ChatGPT and save each reply where the
# manual (ChatGPT web) step would save it, so collect.py / cot_check.py / score.py read them unchanged.
# Usage (from the folder that contains code/ and work/):
#   python code/gpt_api.py --round 1          every work/gpt/prompts/round1_type*.txt that has no reply yet
#   python code/gpt_api.py --cot 1            every work/gpt/prompts/cot_round1_part*.txt that has no reply yet
#   python code/gpt_api.py round1_type3       named prompts only
#   python code/gpt_api.py --prompt-file work/chatgpt_50questions/prompt_chatgpt.txt --out-file work/chatgpt_50questions/answers_chatgpt.txt
# API key: environment variable OPENAI_API_KEY, or the file ~/.openai/key.txt (key only). The key is never printed.
# Every call is logged (time, model, prompt, tokens) to work/gpt/responses/chatgpt_log.txt.
import argparse
import datetime
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = 'work/gpt'
ap = argparse.ArgumentParser()
ap.add_argument('names', nargs='*')
ap.add_argument('--round', type=int)
ap.add_argument('--cot', type=int)
ap.add_argument('--model', default='gpt-4o')
ap.add_argument('--overwrite', action='store_true')
ap.add_argument('--prompt-file')
ap.add_argument('--out-file')
a = ap.parse_args()


def api_key():
    k = os.environ.get('OPENAI_API_KEY', '').strip()
    if not k:
        p = os.path.join(os.path.expanduser('~'), '.openai', 'key.txt')
        if os.path.exists(p):
            k = open(p, encoding='utf-8-sig').read().strip()
    if not k:
        sys.exit('no API key: set OPENAI_API_KEY or create ~/.openai/key.txt')
    return k


jobs = [(f'{ROOT}/prompts/{n.removesuffix(".txt")}.txt', f'{ROOT}/responses/{n.removesuffix(".txt")}.txt') for n in a.names]
if a.round:
    jobs += [(p, f'{ROOT}/responses/{os.path.basename(p)}') for p in sorted(glob.glob(f'{ROOT}/prompts/round{a.round}_type*.txt'))]
if a.cot:
    jobs += [(p, f'{ROOT}/responses/{os.path.basename(p)}') for p in sorted(glob.glob(f'{ROOT}/prompts/cot_round{a.cot}_part*.txt'))]
if a.prompt_file:
    jobs = [(a.prompt_file, a.out_file)]
if not jobs:
    sys.exit('no prompt selected')
key = api_key()
os.makedirs(f'{ROOT}/responses', exist_ok=True)
log = open(f'{ROOT}/responses/chatgpt_log.txt', 'a', encoding='utf-8')
for pf, reply in jobs:
    name = os.path.basename(pf)[:-4]
    if os.path.exists(reply) and os.path.getsize(reply) > 0 and not a.overwrite:
        print(f'skip {name}: reply exists')
        continue
    body = json.dumps({'model': a.model, 'messages': [{'role': 'user', 'content': open(pf, encoding='utf-8').read()}]}).encode('utf-8')
    req = urllib.request.Request('https://api.openai.com/v1/chat/completions', data=body,
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                res = json.loads(r.read().decode('utf-8'))
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode('utf-8', 'replace')[:300]
            if e.code in (429, 500, 502, 503) and 'insufficient_quota' not in msg and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            sys.exit(f'API error {e.code} at {name}: {msg}')
    text = res['choices'][0]['message']['content']
    os.makedirs(os.path.dirname(reply) or '.', exist_ok=True)
    open(reply, 'w', encoding='utf-8').write(text)
    u = res.get('usage', {})
    log.write(f'{datetime.datetime.now():%Y-%m-%d %H:%M}\tAPI\t{res.get("model", a.model)}\t{name}\t'
              f'in={u.get("prompt_tokens")}\tout={u.get("completion_tokens")}\n')
    log.flush()
    print(f'{name}: {len(text)} chars, model {res.get("model")}, tokens in {u.get("prompt_tokens")} out {u.get("completion_tokens")}')
print('done')
