"""Independent fixture oracles for retained-byte recovery and distinct live faults."""
from copy import deepcopy
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import pytest
from assertions import report_text
from test_14_corrections import data as prior_data,export_snapshot

FIXTURE=Path(__file__).parent/'fixtures/recovery'
ORACLE=json.loads((FIXTURE/'oracle.json').read_text())
TABLES=['campaigns','datasets','runs','decisions','jobs','job_attempts','ingest_sessions','ingest_sources','ingest_attempts','events']


def setup(client):
    shutil.copyfile(FIXTURE/'study.db',client.db);os.chown(client.db,client.uid,client.uid)
    return ORACLE


def state(path):
    with sqlite3.connect(path) as db:
        db.row_factory=sqlite3.Row
        return {table:[dict(r) for r in db.execute('SELECT * FROM '+table)] for table in TABLES}


def canonical(value):
    return sorted(json.dumps(v,sort_keys=True,default=lambda b:{'bytes':bytes(b).hex()}) for v in value)


def command(client,dry=False,backup=None,ok=True):
    args=['evidence-recover','--db',client.db]
    if dry:args+=['--dry-run']
    if backup is not None:args+=['--backup',backup]
    return client.command(*args,ok=ok)


def entries(report):
    assert report['version']=='transfer-evidence-v1'
    result={s['campaign']:s for s in report['studies']}
    assert len(result)==len(report['studies'])==ORACLE['count']
    assert set(result)=={c['campaign'] for c in ORACLE['cases']}
    return result


def check_plan(report,applied=False):
    by=entries(report)
    for case in ORACLE['cases']:
        e=by[case['campaign']]
        blocked=case['blocked'] and not (case['kind']=='later_direct' and e['status'] in {'recoverable','recovered'})
        expected='blocked' if blocked else ('recovered' if applied else 'recoverable') if case['sessions'] else 'unaffected'
        assert e['status']==expected,(case['campaign'],case['kind'],e)
        assert {s['session'] for s in e['sessions']}==(set(case['sessions']) if not blocked else set())
        assert {j['job'] for j in e['jobs']}==({j['job'] for j in case['repin']} if not blocked else set())
        if not blocked:
            session_map={s['session']:s['to_dataset'] for s in e['sessions']}
            job_map={j['job']:j['to_dataset'] for j in e['jobs']}
            for intended in case['repin']:assert job_map[intended['job']]==session_map[intended['session']]
        assert bool(e['unresolved'])==blocked
        expected_runs=[r for r in ORACLE['original']['runs'] if r['campaign']==case['campaign']]
        expected_decisions=[d for d in ORACLE['original']['decisions'] if d['campaign']==case['campaign']]
        assert {(r['run'],r['dataset'],r['action']) for r in e['runs']}=={(r['id'],r['dataset'],'preserved') for r in expected_runs}
        assert {(d['decision'],d['run'],d['action']) for d in e['decisions']}=={(d['id'],d['run'],'preserved') for d in expected_decisions}
    return by


def assert_apply(client,before,report):
    by=check_plan(report,True);after=state(client.db)
    for table in ['campaigns','runs','decisions','job_attempts','ingest_sources','ingest_attempts']:
        fields=set(before[table][0]) if before[table] else set()
        assert canonical([{k:row[k] for k in fields} for row in after[table]])==canonical(before[table]),table
    existing={d['id']:d for d in after['datasets']}
    for d in before['datasets']:assert {k:existing[d['id']][k] for k in d}==d
    oldevents={e['id']:e for e in after['events']}
    for e in before['events']:assert {k:oldevents[e['id']][k] for k in e}==e
    newevents=[e for e in after['events'] if e['id'] not in {o['id'] for o in before['events']}]
    recovered=[c for c in ORACLE['cases'] if by[c['campaign']]['status']=='recovered']
    completions=[e for e in newevents if e['action']=='transfer_evidence_recovered_v1']
    assert sorted(e['campaign'] for e in completions)==sorted(c['campaign'] for c in recovered)
    session_rows={s['id']:s for s in after['ingest_sessions']};job_rows={j['id']:j for j in after['jobs']}
    targetmap={};jobmap={}
    for case in recovered:
        entry=by[case['campaign']]
        changes={s['session']:s for s in entry['sessions']}
        previous=max(d['revision'] for d in before['datasets'] if d['campaign']==case['campaign'])
        for offset,sid in enumerate(case['sessions'],1):
            change=changes[sid];target=change['to_dataset'];targetmap[sid]=target
            row=existing[target];content=case['expected_contents'][sid]
            expected_sha=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            assert row['revision']==change['revision'] and row['revision']>previous
            assert json.loads(row['content'])==content and row['sha']==change['sha256']==expected_sha
            assert session_rows[sid]['published_dataset']==target
        revisions=[existing[c['to_dataset']]['revision'] for c in changes.values()]
        assert len(set(revisions))==len(revisions)
        assert client.show(case['campaign'])['current_review'] is None
        if case['kind']=='later_direct':
            direct=max((d for d in before['datasets'] if d['campaign']==case['campaign']),key=lambda d:d['revision'])
            assert direct['id'] in existing
        for intended in case['repin']:jobmap[intended['job']]=targetmap[intended['session']]
    assert len(after['datasets'])==len(before['datasets'])+len(targetmap)
    for old in before['jobs']:
        expected=dict(old,dataset=jobmap.get(old['id'],old['dataset']))
        assert {k:job_rows[old['id']][k] for k in old}==expected,old['id']
    for old in before['ingest_sessions']:
        expected=dict(old,published_dataset=targetmap.get(old['id'],old['published_dataset']))
        assert {k:session_rows[old['id']][k] for k in old}==expected,old['id']
    for case in recovered:
        if case['kind']=='later_direct':
            direct=max((d for d in before['datasets'] if d['campaign']==case['campaign']),key=lambda d:d['revision'])
            policy=client.write('direct-preservation-policy.json',{'max_ic50_um':2.625})
            new=client.command('job-submit','--db',client.db,'--campaign',case['campaign'],'--policy',policy)
            assert client.sql('SELECT dataset FROM jobs WHERE id=?',(new['job'],))[0]['dataset']==direct['id']
    return by


def test_scheduler_submission_identity_includes_the_dataset(client):
    c=client.create('screening');client.import_data(c,prior_data())
    old=client.command('job-submit','--db',client.db,'--campaign',c)['job']
    # Exercise a genuine published revision, including its durable journal entry.
    revision=client.import_data(c,prior_data('corrected.json'))
    assert not revision['reused']
    new=client.command('job-submit','--db',client.db,'--campaign',c)
    assert new['job']!=old and not new['reused']
    assert client.sql('SELECT dataset FROM jobs WHERE id=?',(new['job'],))[0]['dataset']==revision['dataset']
    assert client.command('job-submit','--db',client.db,'--campaign',c)['job']==new['job']


def test_equal_dose_records_are_not_aggregated_in_evidence_exports(client):
    d=prior_data();c=client.create('screening');client.import_data(c,d);run=client.run(c)['run']
    snapshot,directory=export_snapshot(client,c,run,'per-well')
    bindings=snapshot['analysis']['result']['transfer_history'][0]['bindings']
    assert {b['record_id'] for b in bindings}=={'early','late'}
    rows=list(csv.DictReader((directory/'transfer-bindings.csv').open()))
    assert len(rows)==len(bindings)
    assert all(any(b['record_id'] in row.values() for row in rows) for b in bindings)
    text=report_text((directory/'index.html').read_text())
    assert 'early' in text and 'late' in text


def test_dry_run_identifies_recoverable_blocked_and_healthy_without_writes(client):
    setup(client);before=Path(client.db).read_bytes()
    result=command(client,dry=True)
    assert result['mode']=='dry_run' and result['backup'] is None
    check_plan(result)
    assert Path(client.db).read_bytes()==before


def test_apply_recovers_ordered_revisions_and_preserves_original_work(client):
    setup(client);before=state(client.db);planned=command(client,dry=True)
    backup=client.directory/'pre-recovery.db';applied=command(client,backup=backup)
    assert_apply(client,before,applied)
    assert canonical(state(backup)['events'])==canonical(before['events'])
    assert state(backup)==before
    plan_entries=entries(planned);applied_entries=entries(applied)
    for cid,p in plan_entries.items():
        applied_entry=applied_entries[cid]
        assert {s['session']:{k:v for k,v in s.items() if k!='to_dataset'} for s in p['sessions']}=={s['session']:{k:v for k,v in s.items() if k!='to_dataset'} for s in applied_entry['sessions']}
        assert {j['job']:{k:v for k,v in j.items() if k!='to_dataset'} for j in p['jobs']}=={j['job']:{k:v for k,v in j.items() if k!='to_dataset'} for j in applied_entry['jobs']}


def test_recovery_is_idempotent_and_reported_mappings_remain_consistent(client):
    setup(client);first=command(client,backup=client.directory/'first-backup.db')
    check_plan(first,True);before=state(client.db)
    dry=command(client,dry=True);repeat=command(client,backup=client.directory/'second-backup.db')
    by=entries(repeat)
    for case in ORACLE['cases']:
        e=by[case['campaign']]
        if entries(first)[case['campaign']]['status']=='recovered':
            assert e['status']=='already_recovered'
            original=entries(first)[case['campaign']]
            assert canonical(e['sessions'])==canonical(original['sessions']) and canonical(e['jobs'])==canonical(original['jobs'])
    assert state(client.db)==before
    assert {e['campaign']:e['status'] for e in dry['studies']}=={e['campaign']:e['status'] for e in repeat['studies']}


def test_cached_parses_and_row_enumeration_order_are_not_recovery_evidence(client):
    setup(client)
    client.sql("UPDATE ingest_sources SET parsed='[]'")
    client.sql("UPDATE events SET created='unreliable-time'")
    before=state(client.db)
    result=command(client,backup=client.directory/'backup.db')
    assert_apply(client,before,result)


def test_apply_refuses_missing_or_existing_backup_without_mutation(client):
    setup(client);before=state(client.db)
    command(client,ok=False)
    existing=client.directory/'already-there.db';existing.write_bytes(b'preserve this file');os.chown(existing,client.uid,client.uid)
    command(client,backup=existing,ok=False)
    assert existing.read_bytes()==b'preserve this file' and state(client.db)==before


def test_recovery_interruption_rolls_back_all_changes_and_retains_backup(client):
    setup(client)
    client.sql("CREATE TRIGGER recovery_stop BEFORE INSERT ON datasets BEGIN SELECT RAISE(ABORT,'controlled recovery interruption'); END")
    before=state(client.db);backup=client.directory/'backup.db'
    command(client,backup=backup,ok=False)
    assert backup.is_file() and state(client.db)==before
    assert state(backup)==before
    client.sql('DROP TRIGGER recovery_stop')
    assert_apply(client,before,command(client,backup=client.directory/'retry-backup.db'))


def test_recovered_queued_jobs_use_their_own_publication_epoch(client):
    setup(client);report=command(client,backup=client.directory/'backup.db');check_plan(report,True)
    chain=next(c for c in ORACLE['cases'] if c['kind']=='merged_chain')
    for position,intended in enumerate(chain['repin']):
        job=intended['job'];lease=client.command('job-claim','--db',client.db,'--job',job,'--worker','recovered')
        client.command('job-compute','--db',client.db,'--job',job,'--token',lease['token'])
        staged=json.loads(client.sql('SELECT staged FROM jobs WHERE id=?',(job,))[0]['staged'])
        evidence=staged['result']['transfer_history'][0]
        bound=next(b for b in evidence['bindings'] if b['record_id']=='early')
        assert bound['volume_ul']==pytest.approx(16 if position==0 else 24)
        result=client.command('job-publish','--db',client.db,'--job',job,'--token',lease['token'])
        snapshot,_=export_snapshot(client,chain['campaign'],result['run'],'recovered-'+str(position))
        assert snapshot['input']==chain['expected_contents'][intended['session']]
