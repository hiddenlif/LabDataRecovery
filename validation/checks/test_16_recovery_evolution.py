"""Independent normalized-input expectations for distinct recovery histories."""
import json, os, shutil, sqlite3, hashlib
from pathlib import Path
import pytest
from test_15_recovery_migration import state, canonical, command
F=Path(__file__).parent/'fixtures/evolution'
O=json.loads((F/'oracle.json').read_text())

def setup(client):
    shutil.copyfile(F/'study.db',client.db);os.chown(client.db,client.uid,client.uid)
    return state(client.db)

def apply(client):
    return command(client,backup=client.directory/'backup.db')

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def verify(client,kind):
    before=setup(client);report=apply(client);entries={e['campaign']:e for e in report['studies']}
    after=state(client.db);datasets={r['id']:r for r in after['datasets']};sessions={r['id']:r for r in after['ingest_sessions']};jobs={r['id']:r for r in after['jobs']}
    for case in O['cases']:
        if case['kind']!=kind:continue
        cid=case['campaign'];entry=entries[cid]
        if case['blocked']:
            assert entry['status']=='blocked' and entry['unresolved']
            for table in ['datasets','jobs','ingest_sessions','events']:
                assert canonical([r for r in before[table] if r.get('campaign')==cid])==canonical([r for r in after[table] if r.get('campaign')==cid])
            continue
        assert entry['status']=='recovered',entry
        for sid,expected in case['expected_sessions'].items():
            target=sessions[sid]['published_dataset'];actual=datasets[target]
            assert json.loads(actual['content'])==expected,(kind,sid)
            assert actual['sha']==digest(expected)
            if sid in case['adopted']:assert target==case['adopted'][sid], 'Must adopt verified old progress'
        for job,sid in case['pins'].items():assert jobs[job]['dataset']==sessions[sid]['published_dataset'],(kind,job)
        expected_current=sessions[case['current_session']]['published_dataset']
        # Exercise a real new submission: no implementation-specific pointer spelling.
        policy=client.write('new-policy.json',{'max_ic50_um':3.125})
        result=client.command('job-submit','--db',client.db,'--campaign',cid,'--policy',policy)
        pin=client.sql('SELECT dataset FROM jobs WHERE id=?',(result['job'],))[0]['dataset']
        assert pin==expected_current,'New work must use latest published evidence'
        old={d['id'] for d in before['datasets'] if d['campaign']==cid}
        added=[d for d in after['datasets'] if d['campaign']==cid and d['id'] not in old]
        expected_new=sum(sid not in case['adopted'] and not any(d['sha']==digest(content) for d in before['datasets'] if d['campaign']==cid) for sid,content in case['expected_sessions'].items())
        assert len(added)==expected_new,'Recovery must not duplicate verified revisions'

@pytest.mark.parametrize('kind',['legacy','partial','mixed','unknown_codec'])
def test_recovery_history_semantics(client,kind):verify(client,kind)

def test_repeat_adopts_partial_progress_without_new_changes(client):
    setup(client);first=apply(client);before=state(client.db)
    repeat=command(client,backup=client.directory/'backup-repeat.db')
    assert state(client.db)==before
    selected={c['campaign'] for c in O['cases'] if not c['blocked']}
    assert all(e['status']=='already_recovered' for e in repeat['studies'] if e['campaign'] in selected)

def test_evolution_preserves_all_preexisting_evidence_and_worker_state(client):
    before=setup(client);apply(client);after=state(client.db)
    for table in ['campaigns','runs','decisions','job_attempts','ingest_sources','ingest_attempts']:
        assert canonical(before[table])==canonical(after[table]),table
    for table in ['datasets','events']:
        by={r['id']:r for r in after[table]}
        assert all(by[r['id']]==r for r in before[table]),table
    by={r['id']:r for r in after['jobs']}
    for old in before['jobs']:
        if old['state']!='queued':assert by[old['id']]==old

def test_evolution_dry_run_backup_and_plan_consistency(client):
    before=setup(client);raw=Path(client.db).read_bytes();plan=command(client,dry=True)
    assert Path(client.db).read_bytes()==raw
    actual=apply(client)
    assert state(client.directory/'backup.db')==before
    by={e['campaign']:e for e in actual['studies']}
    for entry in plan['studies']:
        applied=by[entry['campaign']]
        assert entry['status']=={'recovered':'recoverable'}.get(applied['status'],applied['status'])
        assert {(s['session'],s['sha256'],s['revision']) for s in entry['sessions']}=={(s['session'],s['sha256'],s['revision']) for s in applied['sessions']}


def test_mixed_history_refresh_analyze_review_and_subsequent_import(client):
    setup(client);apply(client)
    for case in O['cases']:
        if case['kind']!='mixed':continue
        cid=case['campaign'];shown=client.show(cid)
        run=client.run(cid)['run']
        decision=client.review(cid,run,shown['current_revision'])
        assert client.show(cid)['current_review']['id']==decision['decision']
        sid=case['current_session']
        content=case['expected_sessions'][sid]
        repeated=client.import_data(cid,content)
        assert repeated['reused']
        assert client.show(cid)['current_review']['id']==decision['decision']
        changed=json.loads(json.dumps(content));changed['records'][-1]['signal']+=13
        imported=client.import_data(cid,changed)
        assert not imported['reused']
        assert client.show(cid)['current_review'] is None
        policy=client.write('post-policy.json',{'max_ic50_um':2.375})
        new=client.command('job-submit','--db',client.db,'--campaign',cid,'--policy',policy)
        assert client.sql('SELECT dataset FROM jobs WHERE id=?',(new['job'],))[0]['dataset']==imported['dataset']
