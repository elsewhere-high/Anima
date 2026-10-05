"""Fixed current-state test, validation-only temperature; task-level retention gates."""
import sys, json, time, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'v3/scripts')]
import numpy as np
import torch
from sklearn.metrics import classification_report, f1_score
from social_v4.runtime_model import SharedModel, STATE_LABELS, V2
from social_world_zh.model import checkpoint_fingerprint
from evaluate import metrics, softmax, VALENCE_GROUPS, bootstrap_accuracy


def main():
    torch.set_num_threads(4)
    start = time.time()
    folder = ROOT / 'runs/current_state_lora'
    selection = json.loads((folder / 'selection.json').read_text())
    report_path = ROOT / 'reports/current_state_evaluation.json'
    if report_path.exists():
        raise RuntimeError('Fixed-test evaluation already exists')
    protocol = {
        'checkpoint_selection': 'Completed training validation only; no test-driven retraining in this run',
        'calibration': 'Scalar temperature minimizes CPED validation NLL; no class bias or argmax changes',
        'task_release': {'emotion': 'CPED accuracy >= same-execution original -.005, macro F1 >= original +.01; MEDD accuracy >= original -.005',
                         'dialog_act': 'CPED accuracy and macro F1 >= original -.005',
                         'sentiment': 'CPED accuracy and macro F1 >= original probability-grouped CPED sentiment -.005'},
        'other_tasks': 'Always original V2 adapter/heads; candidate state adapter cannot mutate intent/policy route',
        'test_labels_changed': False,
        'cped_test_previously_inspected': True,
        'medd_test_newly_reserved': True,
        'field_validation': False}
    (folder / 'evaluation_protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    if not selection['checkpoint']:
        report_path.write_text(json.dumps({'status': 'no_validation_qualified_checkpoint', 'accepted_heads': [], 'protocol': protocol}, indent=2), encoding='utf-8')
        return
    checkpoint = Path(selection['checkpoint'])
    model = SharedModel(state_checkpoint=checkpoint)
    original_temperatures = json.loads((V2 / 'reports/calibration.json').read_text())['temperatures']
    manifest = json.loads((ROOT / 'data/state/manifest.json').read_text())
    def collect(split):
        file = ROOT / 'data/state' / (split + '.jsonl')
        assert hashlib.sha256(file.read_bytes()).hexdigest() == manifest['files'][split]['sha256']
        rows = [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
        tokens = model.tokenizer([r['text'] for r in rows], truncation=True, max_length=256)['input_ids']
        order = sorted(range(len(rows)), key=lambda i: len(tokens[i]))
        original = {k: np.zeros((len(rows), len(labels)), np.float32) for k, labels in STATE_LABELS.items()}
        trained = {k: np.zeros_like(x) for k, x in original.items()}
        with torch.inference_mode():
            for pos in range(0, len(order), 16):
                ix = order[pos:pos + 16]
                inputs = model.tokenizer.pad({'input_ids': [tokens[i] for i in ix]}, padding=True, pad_to_multiple_of=8, return_tensors='pt').to('cuda')
                a = model.original_logits(**inputs)
                b = model.state_logits(**inputs)
                for k in trained:
                    trained[k][ix] = b[k].cpu().numpy()
                    if k != 'sentiment': original[k][ix] = (a[k] / original_temperatures[k]).cpu().numpy()
                # Original V2 sentiment is the sum of calibrated emotion probabilities.
                temperature = original_temperatures['emotion']
                p = (a['emotion'] / temperature).softmax(-1).cpu().numpy()
                original['sentiment'][ix] = np.log(np.stack([p[:, group].sum(-1) for group in VALENCE_GROUPS], -1).clip(1e-12))
        np.savez_compressed(folder / (split + '_current_logits.npz'), **{'original_' + k: v for k, v in original.items()}, **{'trained_' + k: v for k, v in trained.items()})
        (folder / (split + '_current_ids.json')).write_text(json.dumps([r['id'] for r in rows]), encoding='utf-8')
        return rows, original, trained
    val, old_val, new_val = collect('validation')
    temperatures = {}
    for k in STATE_LABELS:
        ix = [i for i, r in enumerate(val) if r['source'] == 'cped_state' and k in r['labels']]
        y = np.array([val[i]['labels'][k] for i in ix])
        grid = np.exp(np.linspace(np.log(.3), np.log(5.), 80))
        temperatures[k] = float(min(grid, key=lambda t: metrics(y, new_val[k][ix] / t)['nll']))
    fingerprint = checkpoint_fingerprint(checkpoint)
    calibration = {'checkpoint_fingerprint': fingerprint, 'temperatures': temperatures, 'fit_split': 'cped_validation_only', 'argmax_changed': False}
    (folder / 'calibration.json').write_text(json.dumps(calibration, indent=2), encoding='utf-8')
    rows, old, new = collect('test')
    training_counts = json.loads((ROOT / 'reports/state_training_label_counts.json').read_text())
    results = {}
    for source in ['cped_state', 'chinese_medd']:
        results[source] = {}
        for k, names in STATE_LABELS.items():
            ix = [i for i, r in enumerate(rows) if r['source'] == source and k in r['labels']]
            if not ix: continue
            selected = [rows[i] for i in ix]
            y = np.array([r['labels'][k] for r in selected]); a = old[k][ix]; b = new[k][ix] / temperatures[k]
            d = {'original': metrics(y, a), 'trained': metrics(y, b), 'label_count': len(names), 'per_class': classification_report(y, b.argmax(-1), labels=list(range(len(names))), target_names=names, output_dict=True, zero_division=0)}
            counts = training_counts[source][k]
            majority = max(counts, key=counts.get)
            constant = np.full_like(y, names.index(majority))
            d['train_majority_reference'] = {'label': majority, 'accuracy': float((constant == y).mean()), 'macro_f1': float(f1_score(y, constant, labels=list(range(len(names))), average='macro', zero_division=0))}
            d['accuracy_delta_95ci'] = bootstrap_accuracy(selected, y, b.argmax(-1), a.argmax(-1))
            if source == 'chinese_medd' and k == 'emotion':
                active = sorted(set(y.tolist()))
                d['active_label_ids'] = active
                d['active_six_class_macro_f1'] = {label: float(f1_score(y, x.argmax(-1), labels=active, average='macro', zero_division=0)) for label, x in [('original', a), ('trained', b)]}
            results[source][k] = d
    c = results['cped_state']; e = results['chinese_medd']['emotion']
    accepted = []
    if c['emotion']['trained']['accuracy'] >= c['emotion']['original']['accuracy'] - .005 and c['emotion']['trained']['macro_f1'] >= c['emotion']['original']['macro_f1'] + .01 and e['trained']['accuracy'] >= e['original']['accuracy'] - .005:
        accepted.append('emotion')
    for k in ['dialog_act', 'sentiment']:
        if all(c[k]['trained'][m] >= c[k]['original'][m] - .005 for m in ['accuracy', 'macro_f1']): accepted.append(k)
    result = {'status': 'evaluated', 'checkpoint': str(checkpoint), 'checkpoint_fingerprint': fingerprint, 'accepted_heads': accepted, 'metrics': results, 'calibration': calibration, 'protocol': protocol, 'seconds': time.time() - start, 'peak_vram_mib': torch.cuda.max_memory_allocated() / 2**20, 'test_files': manifest['files']['test']}
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['accepted_heads', 'seconds', 'peak_vram_mib']}), flush=True)
    print(json.dumps({s: {k: {q: d[q] for q in ['original', 'trained']} for k, d in v.items()} for s, v in results.items()}), flush=True)


if __name__ == '__main__': main()
