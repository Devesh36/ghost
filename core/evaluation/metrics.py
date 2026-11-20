"""Separate target-rule classification, workflow results and incomplete execution."""


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def detection_metrics(rows):
    counts = {name: 0 for name in ('tp', 'fp', 'tn', 'fn', 'unscored')}
    for row in rows:
        observed = row['observed']
        if observed is None:
            counts['unscored'] += 1
        else:
            counts[('t' if observed == row['expected'] else 'f') + ('p' if observed else 'n')] += 1
    tp, fp, tn, fn = (counts[key] for key in ('tp', 'fp', 'tn', 'fn'))
    return {**counts, 'total': len(rows), 'scored': tp + fp + tn + fn,
            'coverage': ratio(tp + fp + tn + fn, len(rows)),
            'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn),
            'false_positive_rate': ratio(fp, fp + tn),
            'complete': counts['unscored'] == 0 and bool(rows)}


def workflow_metrics(rows):
    passed = sum(row['outcome'] == 'passed' for row in rows)
    failed = sum(row['outcome'] == 'failed' for row in rows)
    return {'total': len(rows), 'passed': passed, 'failed': failed,
            'incomplete': len(rows) - passed - failed,
            'pass_rate': ratio(passed, passed + failed),
            'coverage': ratio(passed + failed, len(rows))}


def summarize(detection, repairs, evidence):
    detection_score = detection_metrics(detection)
    repair_score = workflow_metrics(repairs)
    evidence_score = workflow_metrics(evidence)
    # Refusals are not successful repairs; seed candidates are never included in
    # the end-to-end solver denominator. Undefined rates stay null, not 100%.
    repair_score['eligible_repairs'] = workflow_metrics([r for r in repairs if r['expected'] == 'verified'])
    repair_score['scope_refusals'] = workflow_metrics([r for r in repairs if r['expected'] == 'blocked'])
    evidence_score['negative_controls'] = workflow_metrics([r for r in evidence if r['expected'] != 'supported'])
    evidence_score['false_supports'] = sum(r['actual'] == 'supported' and r['expected'] != 'supported'
                                           for r in evidence if r['outcome'] != 'incomplete')
    incomplete = (not detection_score['complete'] or repair_score['incomplete']
                  or evidence_score['incomplete'] or not repairs or not evidence)
    gaps = detection_score['fp'] + detection_score['fn'] + repair_score['failed'] + evidence_score['failed']
    return {'detection': detection_score, 'repairs': repair_score, 'evidence': evidence_score,
            'complete': not bool(incomplete), 'gaps': gaps,
            'exit_code': 2 if incomplete else 1 if gaps else 0}
