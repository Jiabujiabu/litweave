"""Score independent human labels against a saved ranking, never the shuffled row order."""
import argparse
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from evaluation import relevance_metrics, save_run


def load_human_labels(csv_path, mapping):
    allowed = {'direct','partial','irrelevant','insufficient_information',''}
    seen, labels = set(), {}
    with Path(csv_path).open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            bid, value = row['blind_id'], row['human_label'].strip()
            if bid not in mapping or bid in seen or value not in allowed:
                raise ValueError('unknown/duplicate blind ID or invalid human label')
            seen.add(bid)
            info = mapping[bid]
            labels.setdefault(info['topic'],[]).append({'paper_id':info['paper_id'],
                'label':value or 'unjudged','source':'human' if value else 'none'})
    return labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels',required=True)
    parser.add_argument('--mapping',required=True)
    parser.add_argument('--ranking',required=True,help='JSON list of {topic, ranked_paper_ids}, in saved ranking order')
    parser.add_argument('--k',type=int,default=5)
    args = parser.parse_args()
    mapping = json.loads(Path(args.mapping).read_text(encoding='utf-8'))
    labels = load_human_labels(args.labels,mapping)
    ranking = json.loads(Path(args.ranking).read_text(encoding='utf-8'))
    rows = []
    for case in ranking:
        ids = case['ranked_paper_ids']
        applicable = [j for j in labels.get(case['topic'],[]) if j['paper_id'] in ids]
        rows.append({'topic':case['topic'], 'metrics':relevance_metrics(ids,applicable,args.k,known_relevant_ids=case.get('known_relevant_ids'))})
    print(save_run({'harness':'independent_human_labels','k':args.k,'human_annotation':'provided_labels'}, {'ranking':ranking,'labels':labels},rows,mode='human_offline'))


if __name__ == '__main__':
    main()
