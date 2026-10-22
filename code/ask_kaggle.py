# ask_kaggle.py - Kaggle kernel: ask the fine-tuned model NEW questions. Loads Qwen2.5-7B-Instruct (4-bit) plus the
# LoRA adapter ft7_relcn trained by the nl2gql-dkg kernel (attached as kernel source, no re-training) and writes one
# Cypher query per question, with the same prompt as training (relevant schema with explanations, train_kaggle.py).
# Input: questions.jsonl next to this script's data (id, nl, ctx_rel_cn), made on the local machine by
#        code/ask_pack.py (the relevant schema comes from the same extractor as the test set).
# Output (/kaggle/working): answers_ft7_relcn.txt (lines "Qxx: <Cypher>"), answers_ft7_relcn.jsonl, ask.log
import glob
import json
import os
import re
import subprocess
import sys
import time

T0 = time.time()
OUT = '/kaggle/working'
BASE = 'Qwen/Qwen2.5-7B-Instruct'
JOB = 'ft7_relcn'
TASK = ('You are a graph database expert. Please write the corresponding graph query language '
        '(Neo4j Cypher) based on the relevant schema and natural language. Output only the query.')
QUESTIONS = __QUESTIONS__                                   # filled in by code/ask_pack.py

logf = open(f'{OUT}/ask.log', 'a', encoding='utf-8')


def log(*a):
    s = f'[{round(time.time() - T0)}s] ' + ' '.join(str(x) for x in a)
    print(s, flush=True)
    logf.write(s + '\n')
    logf.flush()


def clean(t):                                               # same as train_kaggle.py
    t = t.strip()
    m = re.search(r'```(?:cypher|sql|gql)?\s*(.*?)```', t, re.S | re.I)
    if m:
        t = m.group(1).strip()
    t = re.sub(r'^```(?:cypher)?', '', t).strip()
    t = re.sub(r'^\[GQL\]:\s*', '', t)
    lines = []
    for ln in t.splitlines():
        if not ln.strip():
            if lines:
                break
            continue
        if ln.strip().startswith('[NL]'):
            break
        lines.append(ln.strip())
    return ' '.join(lines).strip()


subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', '-q', 'torchao'], check=False)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'peft', 'bitsandbytes'], check=False)
import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig  # noqa: E402
from peft import PeftModel  # noqa: E402

hits = glob.glob(f'/kaggle/input/**/adapters/{JOB}/adapter_config.json', recursive=True)
if not hits:
    sys.exit(f'adapter {JOB} not found under /kaggle/input: attach kernel output vanthieu/nl2gql-dkg')
adapter = os.path.dirname(hits[0])
log('gpu', torch.cuda.get_device_name(0), '| adapter', adapter)
dtype = torch.float16
tok = AutoTokenizer.from_pretrained(BASE)
tok.padding_side = 'left'
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
model = AutoModelForCausalLM.from_pretrained(
    BASE, torch_dtype=dtype, device_map={'': 0},
    quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                           bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True))
model = PeftModel.from_pretrained(model, adapter)
model.eval()
log('loaded base + adapter', round(torch.cuda.memory_allocated() / 2**30, 2), 'GiB')


def prompt(x):
    user = f"[Relevant Schema of Graph DB]:\n{x['ctx_rel_cn']}\n\n[Task Description]: {TASK}\n\n[NL]: {x['nl']}\n[GQL]:"
    return tok.apply_chat_template([{'role': 'user', 'content': user}], tokenize=False, add_generation_prompt=True)


t1 = time.time()
BS = 8                                                      # batch of questions per generate call, as in training
with open(f'{OUT}/answers_{JOB}.txt', 'w', encoding='utf-8') as ft, \
        open(f'{OUT}/answers_{JOB}.jsonl', 'w', encoding='utf-8') as fj:
    for i in range(0, len(QUESTIONS), BS):
        batch = QUESTIONS[i:i + BS]
        e = tok([prompt(x) for x in batch], return_tensors='pt', padding=True, add_special_tokens=False).to('cuda')
        with torch.inference_mode(), torch.autocast('cuda', dtype=dtype):
            o = model.generate(**e, max_new_tokens=200, do_sample=False, pad_token_id=tok.pad_token_id)
        for x, r in zip(batch, o):
            raw = tok.decode(r[e['input_ids'].shape[1]:], skip_special_tokens=True)
            pred = clean(raw)
            ft.write(f"{x['id']}: {pred}\n")
            fj.write(json.dumps(dict(id=x['id'], nl=x['nl'], pred=pred, raw=raw), ensure_ascii=False) + '\n')
            log(x['id'], x['nl'], '->', pred)
        ft.flush()
        fj.flush()
log('done', len(QUESTIONS), 'questions in', round(time.time() - t1), 's')
