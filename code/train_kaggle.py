# train_kaggle.py - steps 6 and 8: Kaggle GPU kernel (T4 x2 preferred, 1 GPU works). Fine-tunes Qwen2.5 with (Q)LoRA
# and runs the in-context-learning baseline, then writes predictions for the test questions.
# Jobs (paper Table 4 / Table 8):
#   ft7_relcn  : QLoRA Qwen2.5-7B-Instruct, relevant schema with Chinese explanations (the paper's method)
#   ft7_rel    : same, relevant schema without explanations                    (ablation)
#   ft7_none   : same, no schema                                               (ablation)
#   ft7_full   : same, full schema without explanations                        (ablation)
#   icl7       : ICL baseline, Qwen2.5-7B-Instruct 4-bit, full Chinese schema + K = 8 most similar training pairs
#   ft15_relcn : LoRA Qwen2.5-1.5B-Instruct, relevant Chinese schema           (smaller backbone)
#   icl15      : ICL baseline with Qwen2.5-1.5B-Instruct
# The job list comes from jobs.txt in the dataset (written by kaggle_pack.py). Train questions use the gold relevant
# schema, test questions the extracted one (field ctx_rel_cn / ctx_rel). The kernel reports EM only; EX is computed on
# your machine with score.py because the graph is not uploaded. Predictions: /kaggle/working/preds/<job>.jsonl.
import subprocess, sys, os, json, re, time, random, glob, collections, traceback

T_START = time.time()
DEADLINE_S = 11.2 * 3600          # stop launching / training before Kaggle's 12 h limit
OUT = '/kaggle/working'
SEED = 20261003
JOBS = {
    'ft7_relcn':  dict(model='Qwen/Qwen2.5-7B-Instruct', mode='ft', ctx='rel_cn', q4=True),
    'icl7':       dict(model='Qwen/Qwen2.5-7B-Instruct', mode='icl', ctx='full_cn', q4=True),
    'ft7_none':   dict(model='Qwen/Qwen2.5-7B-Instruct', mode='ft', ctx='none', q4=True),
    'ft7_rel':    dict(model='Qwen/Qwen2.5-7B-Instruct', mode='ft', ctx='rel', q4=True),
    'ft15_relcn': dict(model='Qwen/Qwen2.5-1.5B-Instruct', mode='ft', ctx='rel_cn', q4=False),
    'icl15':      dict(model='Qwen/Qwen2.5-1.5B-Instruct', mode='icl', ctx='full_cn', q4=False),
    'ft7_full':   dict(model='Qwen/Qwen2.5-7B-Instruct', mode='ft', ctx='full', q4=True),
}
EPOCHS, LR, LORA_R, LORA_ALPHA, MAXLEN, K_DEMO = 2, 2e-4, 16, 32, 2048, 8

TASK = ('You are a graph database expert. Please write the corresponding graph query language '
        '(Neo4j Cypher) based on the relevant schema and natural language. Output only the query.')
TASK_FULL = TASK.replace('relevant schema', 'schema')
TASK_NONE = ('You are a graph database expert. Please write the corresponding graph query language '
             '(Neo4j Cypher) for the natural language. Output only the query.')


def find_data():
    hits = glob.glob('/kaggle/input/**/train.jsonl', recursive=True)
    if not hits:
        raise SystemExit('dataset not mounted: check dataset_sources in kernel-metadata.json')
    return os.path.dirname(hits[0])


def job_list():
    p = os.path.join(find_data(), 'jobs.txt')
    names = open(p).read().split() if os.path.exists(p) else list(JOBS)
    return [n for n in names if n in JOBS]


def load(d):
    S = {sp: [json.loads(l) for l in open(f'{d}/{sp}.jsonl', encoding='utf-8')] for sp in ['train', 'dev', 'test']}
    full_cn = open(f'{d}/schema_full_cn.txt', encoding='utf-8').read()
    full = open(f'{d}/schema_full.txt', encoding='utf-8').read()
    return S, full_cn, full


def user_prompt(x, ctx, full_cn, full, demos=None):
    if ctx == 'rel_cn':
        head, task = f"[Relevant Schema of Graph DB]:\n{x['ctx_rel_cn']}\n\n", TASK
    elif ctx == 'rel':
        head, task = f"[Relevant Schema of Graph DB]:\n{x['ctx_rel']}\n\n", TASK
    elif ctx == 'full_cn':
        head, task = f"[Schema of Graph DB]:\n{full_cn}\n\n", TASK_FULL
    elif ctx == 'full':
        head, task = f"[Schema of Graph DB]:\n{full}\n\n", TASK_FULL
    else:
        head, task = '', TASK_NONE
    demo = ''
    if demos:
        demo = '[Demonstrations]:\n' + '\n'.join(f"[NL]: {d['nl']}\n[GQL]: {d['gql']}" for d in demos) + '\n\n'
    return f"{head}[Task Description]: {task}\n\n{demo}[NL]: {x['nl']}\n[GQL]:"


def clean(t):
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


# ---------------- EM (same code as metrics.py) ----------------
CLAUSE_RE = re.compile(r'\b(OPTIONAL MATCH|MATCH|WHERE|WITH|RETURN|ORDER BY|SKIP|LIMIT|UNWIND|UNION)\b', re.I)

def _strip(q):
    q = (q or '').strip()
    m = re.search(r'```(?:cypher|sql|gql)?\s*(.*?)```', q, re.S | re.I)
    if m:
        q = m.group(1)
    q = q.strip().rstrip(';').replace('"', "'").replace('`', '')
    return re.sub(r'\s+', ' ', q)

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
        g = em_components(gold)
        return int(em_components(pred) == g and len(g) > 0)
    except Exception:
        return 0


# ---------------- worker ----------------
def run_job(name, gpu_label):
    cfg = JOBS[name]
    os.makedirs(f'{OUT}/preds', exist_ok=True); os.makedirs(f'{OUT}/logs', exist_ok=True)
    pred_path = f'{OUT}/preds/{name}.jsonl'
    logf = open(f'{OUT}/logs/{name}.log', 'a', encoding='utf-8')
    def log(*a):
        s = f'[{round(time.time() - T_START)}s] ' + ' '.join(str(x) for x in a)
        print(f'{name}: {s}', flush=True); logf.write(s + '\n'); logf.flush()
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, get_cosine_schedule_with_warmup
    d = find_data()
    S, full_cn, full = load(d)
    test = S['test']
    done = set()
    if os.path.exists(pred_path):
        done = {json.loads(l)['id'] for l in open(pred_path, encoding='utf-8')}
    if len(done) >= len(test):
        log('already complete'); return
    log('gpu', gpu_label, torch.cuda.get_device_name(0), 'cfg', cfg)
    random.seed(SEED); torch.manual_seed(SEED)
    cap = torch.cuda.get_device_capability(0)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() and cap[0] >= 8 else torch.float16
    tok = AutoTokenizer.from_pretrained(cfg['model'])
    tok.padding_side = 'left'
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    kw = dict(torch_dtype=dtype, device_map={'': 0})
    if cfg['q4']:
        kw['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                                       bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(cfg['model'], **kw)
    log('loaded', round(torch.cuda.memory_allocated() / 2**30, 2), 'GiB')

    demos_for = {}
    if cfg['mode'] == 'icl':
        from sentence_transformers import SentenceTransformer
        st = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu')
        tr = S['train']
        E_tr = st.encode([x['nl'] for x in tr], normalize_embeddings=True, convert_to_tensor=True)
        E_te = st.encode([x['nl'] for x in test], normalize_embeddings=True, convert_to_tensor=True)
        sims = (E_te @ E_tr.T)
        for i, x in enumerate(test):
            idx = sims[i].topk(K_DEMO).indices.tolist()[::-1]   # most similar demo closest to the query
            demos_for[x['id']] = [tr[j] for j in idx]
        del st

    def msgs(x, demos=None):
        return [{'role': 'user', 'content': user_prompt(x, cfg['ctx'], full_cn, full, demos)}]

    if cfg['mode'] == 'ft':
        adapter_dir = f'{OUT}/adapters/{name}'
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
        if os.path.exists(f'{adapter_dir}/adapter_config.json'):
            model = PeftModel.from_pretrained(model, adapter_dir)
            log('adapter reloaded')
        else:
            if cfg['q4']:
                model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
            else:
                model.gradient_checkpointing_enable(); model.enable_input_require_grads()
            model = get_peft_model(model, LoraConfig(r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=0.05, task_type='CAUSAL_LM',
                                   target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']))
            for _, p in model.named_parameters():
                if p.requires_grad:
                    p.data = p.data.float()
            def enc(x):
                pr = tok.apply_chat_template(msgs(x), tokenize=False, add_generation_prompt=True)
                p = tok(pr, add_special_tokens=False)['input_ids']
                a = tok(x['gql'] + tok.eos_token, add_special_tokens=False)['input_ids']
                return (p + a)[-MAXLEN:], ([-100] * len(p) + a)[-MAXLEN:]
            data = [enc(x) for x in S['train']]
            log('train', len(data), 'mean_len', round(sum(len(a) for a, _ in data) / len(data)))
            BS, ACC = (2, 8) if cfg['q4'] else (4, 4)
            rng = random.Random(SEED)
            steps_per_epoch = len(data) // (BS * ACC)
            total = steps_per_epoch * EPOCHS
            params = [p for p in model.parameters() if p.requires_grad]
            opt = torch.optim.AdamW(params, lr=LR, weight_decay=0.0)
            sch = get_cosine_schedule_with_warmup(opt, max(1, int(0.05 * total)), total)
            scaler = torch.amp.GradScaler('cuda', enabled=(dtype == torch.float16))
            model.train(); step = 0; stop = False
            for ep in range(EPOCHS):
                order = list(range(len(data))); rng.shuffle(order)
                order.sort(key=lambda i: len(data[i][0]) // 64 + rng.random())  # light length bucketing
                batches = [order[i:i + BS] for i in range(0, steps_per_epoch * BS * ACC, BS)]
                rng.shuffle(batches)
                for bi, b in enumerate(batches):
                    batch = [data[i] for i in b]
                    L = max(len(a) for a, _ in batch)
                    ids = torch.tensor([[tok.pad_token_id] * (L - len(a)) + a for a, _ in batch], device='cuda')
                    lab = torch.tensor([[-100] * (L - len(l)) + l for _, l in batch], device='cuda')
                    att = torch.tensor([[0] * (L - len(a)) + [1] * len(a) for a, _ in batch], device='cuda')
                    with torch.autocast('cuda', dtype=dtype):
                        loss = model(input_ids=ids, attention_mask=att, labels=lab).loss / ACC
                    scaler.scale(loss).backward()
                    if (bi + 1) % ACC == 0:
                        scaler.unscale_(opt); torch.nn.utils.clip_grad_norm_(params, 1.0)
                        scaler.step(opt); scaler.update(); opt.zero_grad(set_to_none=True); sch.step(); step += 1
                        if step % 10 == 0:
                            log('epoch', ep, 'step', step, '/', total, 'loss', round(loss.item() * ACC, 4))
                        if time.time() - T_START > DEADLINE_S - 1800:
                            log('deadline reached during training, stopping early at step', step); stop = True; break
                if stop:
                    break
            model.save_pretrained(adapter_dir)
            log('adapter saved, steps', step, 'train_s', round(time.time() - T_START))
        model.eval()
        model.config.use_cache = True

    import torch as _t
    @_t.inference_mode()
    def gen(batch):
        texts = [tok.apply_chat_template(msgs(x, demos_for.get(x['id'])), tokenize=False, add_generation_prompt=True) for x in batch]
        e = tok(texts, return_tensors='pt', padding=True, add_special_tokens=False).to('cuda')
        with _t.autocast('cuda', dtype=dtype):
            o = model.generate(**e, max_new_tokens=200, do_sample=False, pad_token_id=tok.pad_token_id)
        return [tok.decode(r[e['input_ids'].shape[1]:], skip_special_tokens=True) for r in o]

    todo = [x for x in test if x['id'] not in done]
    bs = 4 if (cfg['mode'] == 'icl' or 'full' in cfg['ctx']) else 8
    if not cfg['q4']:
        bs *= 2
    t0 = time.time(); n = 0
    with open(pred_path, 'a', encoding='utf-8') as f:
        for i in range(0, len(todo), bs):
            if time.time() - T_START > DEADLINE_S:
                log('deadline reached during inference'); break
            batch = todo[i:i + bs]
            try:
                raws = gen(batch)
            except Exception as ex:
                log('gen error', repr(ex)[:300]); _t.cuda.empty_cache(); raws = [''] * len(batch)
            for x, r in zip(batch, raws):
                p = clean(r)
                f.write(json.dumps(dict(id=x['id'], type=x['type'], pred=p, raw=r, em=exact_match(p, x['gql'])), ensure_ascii=False) + '\n')
            f.flush(); n += len(batch)
    rows = [json.loads(l) for l in open(pred_path, encoding='utf-8')]
    em = sum(r['em'] for r in rows) / max(1, len(rows))
    log('inference done', n, 'items in', round(time.time() - t0), 's; EM', round(100 * em, 2), 'on', len(rows))


def worker(gpu, names):
    for name in names:
        if time.time() - T_START > DEADLINE_S - 2400:
            print(f'skip {name}: not enough time left', flush=True); continue
        try:
            run_job(name, gpu)
        except Exception:
            traceback.print_exc()
            with open(f'{OUT}/logs/{name}.log', 'a', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        import gc, torch
        gc.collect(); torch.cuda.empty_cache()


def summarize():
    S = {}
    for p in sorted(glob.glob(f'{OUT}/preds/*.jsonl')):
        rows = [json.loads(l) for l in open(p, encoding='utf-8')]
        by = collections.defaultdict(list)
        for r in rows:
            by[r['type']].append(r['em'])
        S[os.path.basename(p)[:-6]] = dict(n=len(rows), EM=round(100 * sum(r['em'] for r in rows) / max(1, len(rows)), 2),
                                            EM_by_type={t: round(100 * sum(v) / len(v), 2) for t, v in sorted(by.items())})
    S['elapsed_s'] = round(time.time() - T_START)
    json.dump(S, open(f'{OUT}/summary_em.json', 'w'), indent=1)
    print(json.dumps(S, indent=1), flush=True)


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--worker':
        worker(sys.argv[2], sys.argv[3].split(','))
        sys.exit(0)
    subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', '-q', 'torchao'], check=False)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'peft', 'bitsandbytes', 'sentence-transformers'], check=False)
    subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', '-q', 'torchao'], check=False)
    os.makedirs(f'{OUT}/logs', exist_ok=True)
    import torch
    ngpu = torch.cuda.device_count()
    print('GPUs', ngpu, [torch.cuda.get_device_name(i) for i in range(ngpu)], flush=True)
    me = os.path.abspath(__file__) if '__file__' in globals() else None
    names = job_list()
    print('jobs', names, flush=True)
    if ngpu >= 2 and me and os.path.exists(me):
        procs = []
        for g in (0, 1):                      # jobs alternate between the two GPUs
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g), PYTHONUNBUFFERED='1')
            procs.append(subprocess.Popen([sys.executable, me, '--worker', str(g), ','.join(names[g::2])], env=env))
        for p in procs:
            p.wait()
    else:
        worker('0', names)
    summarize()
