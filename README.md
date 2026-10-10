# nl2gql-dkg

Reproduction code for Liang et al., *Aligning Large Language Models to a Domain-specific Graph Database for NL2GQL*,
CIKM 2024 ([arXiv:2402.16567](https://arxiv.org/abs/2402.16567)), on the medical knowledge graph DiseaseKG loaded into
Neo4j. Course project of group 14, IS6002.CH191 (Advanced Database Systems).

This repository holds **code only**. It contains no data: DiseaseKG (`medical.json`) is downloaded from
[liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG) in step 1, and every other file
(graph, NL-GQL pairs, schema contexts, predictions, scores) is produced by the steps under `work/`. The source repository
has no licence, so do not publish `medical.json` or anything derived from it.

The step-by-step guide (Vietnamese) downloads each file of `code/` when its step needs it:

| Step | Files | What |
|------|-------|------|
| 2 | `schema.py`, `common.py`, `build_kg.py` | load DiseaseKG into an empty Neo4j database (44,108 nodes, 291,083 relationships) |
| 3 | `templates.py`, `seeds.jsonl`, `gen_prompts.py`, `collect.py`, `cot_check.py`, `ground_split.py` | generate NL-GQL pairs with ChatGPT (self-instruct, CoT check, grounding, 7:1:2 split) |
| 4 | `metrics.py`, `build_contexts.py` | full and relevant schema of every question |
| 5-6 | `kaggle_pack.py`, `train_kaggle.py` | private Kaggle dataset and GPU kernel (QLoRA Qwen2.5-7B, ICL baseline) |
| 7 | `score.py` | EM and EX on Neo4j |
| 8 | `door1_split.py`, `door1_decide.py` | template-disjoint split and pre-registered decision rule |
| 9 | `chatgpt_sheet.py` | 50-question comparison with ChatGPT |

Run every script from the folder that contains `code/`, for example `python code/build_kg.py`. Neo4j connection:
`NEO4J_URI` (default `bolt://localhost:7687`), `NEO4J_DB` (default `diseasekg`), `NEO4J_USER`, `NEO4J_PASSWORD`.
