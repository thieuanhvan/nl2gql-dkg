# nl2gql-dkg

Reproduction code for Liang et al., *Aligning Large Language Models to a Domain-specific Graph Database for NL2GQL*,
CIKM 2024 ([arXiv:2402.16567](https://arxiv.org/abs/2402.16567)), on the medical knowledge graph DiseaseKG loaded into
Neo4j. Course project of group 14, IS6002.26.1.CH.01 (Advanced Database Systems).

This repository holds **code only**. It contains no data: DiseaseKG (`medical.json`) is downloaded from
[liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG) in step 1, and every other file
(graph, NL-GQL pairs, schema contexts, predictions, scores) is produced by the steps under `work/`. The source repository
has no licence, so do not publish `medical.json` or anything derived from it.

**Where the code comes from.** The paper's authors did not release code (their repository holds the StockGQL data
only), so this code was written by the group for the reproduction: Thieu Anh Van together with the AI assistant Claude
(Van asked and reviewed, Claude wrote and test-ran), 3-10 October 2026. Each file follows one part of the paper; the
graph is built as in `build_medicalgraph.py` of the DiseaseKG repository. `door1_split.py`, `door1_decide.py` (a
template-leak check added by the group) and `chatgpt_sheet.py` (a course requirement) are not in the paper. Tag `v1`
was run end to end from an empty folder before publication (the Kaggle GPU part with the same training code earlier).

The step-by-step guide (Vietnamese) downloads each file of `code/` when its step needs it:

| Step | Files | What | Follows |
|------|-------|------|---------|
| 2 | `schema.py`, `common.py`, `build_kg.py` | load DiseaseKG into an empty Neo4j database (44,108 nodes, 291,083 relationships) | build_medicalgraph.py of DiseaseKG |
| 3 | `templates.py`, `seeds.jsonl`, `gen_prompts.py`, `collect.py`, `cot_check.py`, `ground_split.py` | generate NL-GQL pairs with ChatGPT (self-instruct, CoT check, grounding, 7:1:2 split) | paper Sec. 4.1, Tables 10-11 |
| 4 | `metrics.py`, `build_contexts.py` | full and relevant schema of every question | paper Sec. 4.2-4.3 |
| 5-6 | `kaggle_pack.py`, `train_kaggle.py` | private Kaggle dataset and GPU kernel (QLoRA Qwen2.5-7B, ICL baseline) | paper Sec. 4.2 and 5 |
| 7 | `score.py` | EM and EX on Neo4j | paper Sec. 5.1 |
| 3-7 | `demo_steps.py` | follow one test question back through every intermediate file (ChatGPT reply, check, CoT similarity, grounded pairs, relevant schema, prediction, EM/EX); reads files only | group addition |
| 7 | `demo_emex.py` | live demo: record counts, then EM and EX of three test questions (right on both; wrong on EM, right on EX; wrong on both), `--all` re-scores the 296 questions | group addition |
| 8 | `door1_split.py`, `door1_decide.py` | template-disjoint split and pre-registered decision rule | group addition |
| 9 | `chatgpt_sheet.py` | 50-question comparison with ChatGPT | course requirement |
| 3, 9 | `gpt_api.py` | send prompt files to ChatGPT through the OpenAI API and save the replies (tag `v4`) | paper Sec. 4.1 (the paper calls ChatGPT through its API) |
| 3-9 | `run_steps.py` | run a group of steps with the Neo4j password typed once (`data`, `score`, `chatgpt`, `synonym`) | group addition |
| extension | `synonym_test.py`, `aliases_vi.tsv` | normalize everyday disease names before the label linker; 32 hand-written questions | group addition |

Run every script from the folder that contains `code/`, for example `python code/build_kg.py`. Neo4j connection:
`NEO4J_URI` (default `bolt://localhost:7687`), `NEO4J_DB` (default `diseasekg`), `NEO4J_USER`, `NEO4J_PASSWORD`.

## Vietnamese version (tag `v2`)

Set `NL2GQL_LANG=vi` to run the same pipeline in Vietnamese: entity names and short Disease properties are replaced by
their Vietnamese translations when the graph is built, the schema explanations, ChatGPT prompts and the 64 seed
templates (`seeds_vi.jsonl`) are Vietnamese, and string filters compare lowercase text
(`lower(s.name) CONTAINS 'vàng da'`). Labels, relationship types and property names stay in English. The translation
table `data/names_vi.tsv` (kind, Chinese, Vietnamese; 33,250 rows, machine-translated) is derived from `medical.json`,
so it is not in this repository and is shared privately. Long texts (`description`, `cause`, `prevent`) and producer
names stay in Chinese. Without `NL2GQL_LANG` the code behaves exactly as tag `v1`.

Tag `v3` (12 October 2026): with `NL2GQL_LANG=vi` the label linker matches entity names regardless of case, since
Vietnamese names are capitalised in the graph but often written in lower case in questions. Chinese results are unchanged.

Tag `v4` (20 October 2026): ChatGPT through the OpenAI API, as in the paper, instead of pasting prompts into ChatGPT web
(the web route still works: save each reply where `gpt_api.py` would). The API key is read from `OPENAI_API_KEY` or
`~/.openai/key.txt` and never printed; every call (model, tokens) is logged to `work/gpt/responses/chatgpt_log.txt`.
`run_steps.py` checks that Neo4j answers before running, because a run started while the DBMS is still booting rejects
every ChatGPT reply as invalid Cypher. `synonym_test.py` is the group's extension: with the label linker of the paper only
4 of 32 questions written with everyday names (tiểu đường, cao huyết áp, ...) are linked to the right node and ChatGPT's
queries return nothing; after replacing those names with node names, 30 of 32 are linked and all 32 queries are correct.
