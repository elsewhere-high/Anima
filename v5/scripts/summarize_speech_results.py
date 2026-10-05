"""Reproducible diagnostic summaries; never promotes runtime weights."""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/speech_eval'))
from opencc import OpenCC


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        new = [i]
        for j, y in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j-1] + (x != y)))
        row = new
    return row[-1]


def main():
    directory = ROOT / 'reports/speech_20261005'
    cc = OpenCC('t2s')
    probe = json.loads((directory / 'cantonese_evaluation.json').read_text(encoding='utf-8'))
    totals = defaultdict(lambda: [0, 0, 0])
    for r in probe['samples']:
        ref, pred = cc.convert(r['reference']), cc.convert(r['prediction'])
        t = totals[r['corpus'] + '_' + r['language']]
        t[0] += distance(ref, pred); t[1] += len(ref); t[2] += 1
    probe['simplified_script_cer'] = {k: {'cer': e/n, 'errors': e, 'characters': n, 'utterances': u} for k, (e, n, u) in totals.items()}
    probe['script_normalization'] = 'OpenCC t2s, reporting only; literal scores retained'
    (directory / 'cantonese_evaluation.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {}
    for name in ['test_baseline', 'test_selected']:
        path = directory / 'expanded' / (name + '.json')
        if not path.exists():
            continue
        groups = defaultdict(lambda: [0, 0, 0])
        for r in json.loads(path.read_text(encoding='utf-8'))['samples']:
            for group in ['all', 'accent:' + str(r['accent'])]:
                t = groups[group + '/' + r['condition']]
                t[0] += r['errors']; t[1] += r['characters']; t[2] += 1
                ref, pred = cc.convert(r['reference']), cc.convert(r['prediction'])
                t = groups['t2s/' + group + '/' + r['condition']]
                t[0] += distance(ref, pred); t[1] += len(ref); t[2] += 1
        summary[name] = {k: {'cer': e/n, 'errors': e, 'characters': n, 'utterances': u} for k, (e, n, u) in groups.items()}
    (directory / 'expanded/subgroup_results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
