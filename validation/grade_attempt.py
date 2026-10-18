"""Summarize trusted execution evidence by behavioral criterion, without inventing scores."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def summarize(task_id, receipt_directory, inventory_path=None):
    rubric = json.loads((HERE / 'rubric.json').read_text())
    task = next(t for t in rubric['tasks'] if t['id'] == task_id)
    result = json.loads((receipt_directory / 'result.json').read_text())
    cases = list(ET.parse(receipt_directory / 'junit.xml').getroot().iter('testcase'))
    grouped, identities = {}, []
    for case in cases:
        identity = case.attrib['classname'] + '::' + case.attrib['name']
        identities.append(identity)
        key = identity.split('[', 1)[0]
        status = 'error' if case.find('error') is not None else 'failed' if case.find('failure') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
        grouped.setdefault(key, []).append({'case': identity, 'status': status})
    inventory_path = Path(inventory_path) if inventory_path else HERE/'expected-cases.json'
    inventory = json.loads(inventory_path.read_text())
    expected = inventory['profiles'][task['selection']]
    complete = sorted(identities) == sorted(expected) and len(set(identities)) == len(identities)
    evidence_valid = (complete and result.get('selection') == task['selection']
                      and result.get('tests') == len(cases) == result.get('collected')
                      and result.get('image_id') == inventory['image_id']
                      and result.get('source_unchanged') is True
                      and result.get('payload_unchanged') is True
                      and result.get('receipt_copy_exit_code') == 0)
    checks = []
    for criterion in task['criteria']:
        missing = [key for key in criterion['checks'] if key not in grouped]
        observations = [case for key in criterion['checks'] for case in grouped.get(key, [])]
        required_cases = {case for case in expected if case.split('[', 1)[0] in criterion['checks']}
        missing += sorted(required_cases - {case['case'] for case in observations})
        if missing or not observations:
            status = 'not_fully_evaluated'
        elif any(c['status'] in {'error', 'skipped'} for c in observations):
            status = 'inconclusive'
        elif any(c['status'] == 'failed' for c in observations):
            status = 'failed'
        else:
            status = 'passed'
        checks.append({'id': criterion['id'], 'requirement': criterion['requirement'],
                       'status': status, 'missing_checks': missing, 'cases': observations})
    passed = sum(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)
    failed = sum(c.find('failure') is not None for c in cases)
    errors = sum(c.find('error') is not None for c in cases)
    skipped = sum(c.find('skipped') is not None for c in cases)
    counts_agree = all(result.get(k) == v for k,v in {'passed':passed,'failures':failed,'errors':errors,'skipped':skipped}.items())
    evidence_valid = evidence_valid and counts_agree
    functional = (evidence_valid and result.get('accepted') is True and result.get('container_exit_code') == 0
                  and failed == errors == skipped == 0 and all(c['status'] == 'passed' for c in checks))
    return {'task': task_id, 'evidence_consistent': evidence_valid,
            'functional_completion': 'passed' if functional else 'not_established',
            'criteria': checks, 'regression': {'passed':passed,'failed':failed,'errors':errors,'skipped':skipped,
                                              'complete_inventory':complete},
            'manual_review': {'status':'not_reviewed', 'items':rubric['manual_review']},
            'maintainer_acceptance':'not_established_until_manual_review',
            'difficulty':'not_inferred_from_this_receipt',
            'receipt_binding':{name:hashlib.sha256((receipt_directory/name).read_bytes()).hexdigest()
                               for name in ['result.json','junit.xml']},
            'inventory_sha256':hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
            'rubric_sha256':hashlib.sha256((HERE/'rubric.json').read_bytes()).hexdigest(),
            'limit':'Author-side evidence summarizer, not a signature or protection against edited host receipts. Inspect execution logs before attributing failures to a solver.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task')
    parser.add_argument('receipt_directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,help='Author-reviewed inventory from a reproduced package matrix')
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new report path')
    report=summarize(args.task,args.receipt_directory,args.inventory)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k in {'task','functional_completion','maintainer_acceptance'}},indent=2))


if __name__=='__main__':
    main()
