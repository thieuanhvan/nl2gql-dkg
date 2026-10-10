# kaggle_pack.py - steps 5 and 8b: prepare a PRIVATE Kaggle dataset (questions, queries, schema contexts, schema files,
# job list; no graph, no answers) and the kernel folder (train_kaggle.py + kernel-metadata.json) under your Kaggle name.
# Usage: python code/kaggle_pack.py --user <kaggle_user>                  (random split, 7 jobs)
#        python code/kaggle_pack.py --user <kaggle_user> --split door1    (template-disjoint split, 5 jobs)
# Then:  kaggle datasets create -p work/kaggle/<name>-data   and   kaggle kernels push -p work/kaggle/<name>
import argparse
import json
import shutil

from common import ROOT, work

ap = argparse.ArgumentParser()
ap.add_argument('--user', required=True)
ap.add_argument('--split', choices=['random', 'door1'], default='random')
a = ap.parse_args()

if a.split == 'random':
    name, src = 'nl2gql-dkg', 'data_kaggle'
    jobs = ['ft7_relcn', 'icl7', 'ft7_none', 'ft7_rel', 'icl15', 'ft15_relcn', 'ft7_full']
else:
    name, src = 'nl2gql-dkg-d1', 'door1_kaggle'
    jobs = ['ft7_rel', 'ft7_none', 'ft7_full', 'ft7_relcn', 'icl7']

ds = work('kaggle', f'{name}-data', 'x').rsplit('/', 1)[0]
for sp in ['train', 'dev', 'test']:
    shutil.copy(work(src, f'{sp}.jsonl'), ds)
for f in ['schema_full.txt', 'schema_full_cn.txt']:
    shutil.copy(work('schema', f), ds)
open(f'{ds}/jobs.txt', 'w').write('\n'.join(jobs) + '\n')
json.dump({'title': f'{name}-data', 'id': f'{a.user}/{name}-data', 'licenses': [{'name': 'other'}], 'isPrivate': True},
          open(f'{ds}/dataset-metadata.json', 'w'), indent=1)

kd = work('kaggle', name, 'x').rsplit('/', 1)[0]
shutil.copy(ROOT + '/code/train_kaggle.py', kd)
json.dump({'id': f'{a.user}/{name}', 'title': name, 'code_file': 'train_kaggle.py', 'language': 'python',
           'kernel_type': 'script', 'is_private': True, 'enable_gpu': True, 'enable_internet': True,
           'dataset_sources': [f'{a.user}/{name}-data'], 'competition_sources': [], 'kernel_sources': []},
          open(f'{kd}/kernel-metadata.json', 'w'), indent=1)
print('dataset:', ds)
print('kernel :', kd)
print('jobs   :', ' '.join(jobs))
