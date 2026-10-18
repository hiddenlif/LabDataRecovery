"""Evidence identity across revisions, workers, review and portable reports."""
from copy import deepcopy
import csv
import hashlib
import io
from pathlib import Path
import shutil
import sqlite3

import pytest

from truegate.codec import digest, dumps, load, loads
from truegate.engine import analyze
from truegate.errors import Conflict, WorkbenchError
from truegate.ingestion import Ingestion
from truegate.instrument_files import HEADERS
from truegate.jobs import Jobs
from truegate.reporting import export, verify
from truegate.repository import Repository


def evidence():
    records = [dict(id=f'{role}-{i}', plate='P', well=f'{role}-{i}',
                    assay='primary', role=role, signal=signal + i)
               for role, signal in [('vehicle', 10000), ('positive', 100)]
               for i in range(3)]
    records += [dict(id=key, plate='P', well=key, assay='primary', role='sample',
                     signal=signal, compound='X', dose=0, dose_unit='uM')
                for key, signal in [('early', 6000), ('late', 4500)]]
    return {'kind': 'screening', 'records': records, 'transfer_history': {
        'revision': 'original',
        'vessels': [dict(id=key, volume=vol, volume_unit='uL',
                         concentrations=contents, concentration_unit='uM')
                    for key, vol, contents in [('stock', 96, {'X': 73}),
                                               ('well', 0, {}), ('aliquot', 0, {})]],
        'events': [dict(id=key, revision=1, sequence=seq, source=src,
                        destination=dst, status='ok', volume=vol, volume_unit='uL')
                   for key, seq, src, dst, vol in [('load', 1, 'stock', 'well', 24),
                                                  ('take', 2, 'well', 'aliquot', 9)]],
        'bindings': [dict(record_id=key, vessel=vessel, sequence=seq)
                     for key, vessel, seq in [('early', 'well', 1), ('late', 'aliquot', 2)]]}}


def correction(data):
    changed = deepcopy(data)
    history = changed['transfer_history']
    history['revision'] = 'corrected'
    history['events'].insert(0, dict(history['events'][0], revision=2, volume=12))
    return changed


def envelope(data, campaign):
    if not campaign:
        return data
    return {'kind': 'screening', 'campaigns': [dict(
        id='local-study', entities=[dict(local_id='X', type='sequence', value='ACD', target='T')],
        records=data['records'], transfer_history=data['transfer_history'])]}


def observations(analysis):
    return [o for compound in analysis['result']['compounds']
            for channel in compound['channels'].values() for o in channel['observations']]


@pytest.mark.parametrize('campaign_input', [False, True])
@pytest.mark.parametrize('change', ['volume', 'revision', 'order', 'unused_contents'])
def test_changed_evidence_requires_new_review(tmp_path, campaign_input, change):
    original = evidence()
    changed = deepcopy(original)
    history = changed['transfer_history']
    if change == 'volume':
        changed = correction(original)
    elif change == 'revision':
        history['events'][0]['revision'] = 7
    elif change == 'order':
        history['events'].reverse()
    else:
        history['vessels'].append(dict(id='unused', volume=11, volume_unit='uL',
                                       concentrations={'X': 3}, concentration_unit='uM'))
    original, changed = (envelope(d, campaign_input) for d in (original, changed))
    repo = Repository(tmp_path / 'study.db')
    campaign = repo.create('Correction', 'screening')['campaign']
    first = repo.import_data(campaign, original)
    run = repo.run(campaign)['run']
    repo.review(campaign, run, 'accept', 'Reviewer', 'Inspected original', 1)
    before = repo.snapshot(campaign, run)
    assert observations(before['analysis'])
    assert repo.import_data(campaign, deepcopy(original))['reused']
    assert repo.show(campaign)['current_review']['run'] == run

    second = repo.import_data(campaign, changed)
    assert second['revision'] == 2 and not second['reused']
    assert second['sha256'] == digest(changed) != first['sha256']
    assert repo.show(campaign)['current_review'] is None
    with pytest.raises(Conflict):
        repo.review(campaign, run, 'accept', 'Reviewer', 'Stale run', 2)
    new = repo.run(campaign)
    assert [o['dose_um'] for o in observations(new['analysis'])] == pytest.approx([73, 73])
    repo.review(campaign, new['run'], 'hold', 'Reviewer', 'Inspect correction', 2)
    assert repo.import_data(campaign, changed)['reused']
    assert repo.show(campaign)['current_review']['action'] == 'hold'
    assert len(repo.show(campaign)['decisions']) == 2

    historical = repo.snapshot(campaign, run)
    assert historical == dict(before, superseded=True)
    for name, snap in [('before', before), ('historical', historical)]:
        export(snap, tmp_path / name)
        assert verify(tmp_path / name)['verified']
        assert load(tmp_path / name / 'snapshot.json') == snap
    for filename in ['summary.csv', 'transfer-bindings.csv']:
        assert (tmp_path / 'before' / filename).read_bytes() == (tmp_path / 'historical' / filename).read_bytes()
    # Reverting evidence is another revision, not a return to an accepted dataset.
    assert repo.import_data(campaign, original)['revision'] == 3
    assert repo.show(campaign)['current_review'] is None


@pytest.mark.parametrize('compute_before', [False, True])
@pytest.mark.parametrize('existing_run', [False, True])
@pytest.mark.parametrize('campaign_input', [False, True])
def test_jobs_keep_submitted_evidence_and_publication_is_idempotent(
        tmp_path, compute_before, existing_run, campaign_input):
    path = tmp_path / 'jobs.db'
    repo, jobs = Repository(path), Jobs(path)
    campaign = repo.create('Pinned work', 'screening')['campaign']
    original = envelope(evidence(), campaign_input)
    repo.import_data(campaign, original)
    prior_run = repo.run(campaign)['run'] if existing_run else None
    job = jobs.submit(campaign)['job']
    assert jobs.submit(campaign) == {'job': job, 'reused': True}
    token = jobs.claim(job, 'worker', 300)['token']
    if compute_before:
        jobs.compute(job, token)
    repo.import_data(campaign, envelope(correction(evidence()), campaign_input))
    current_run = repo.run(campaign)['run']
    review = repo.review(campaign, current_run, 'accept', 'Reviewer', 'Correction inspected', 2)
    assert jobs.submit(campaign)['job'] != job
    if not compute_before:
        Jobs(path).compute(job, token)
    published = Jobs(path).publish(job, token)
    if existing_run:
        assert published['run'] == prior_run and published['reused']
    snap = Repository(path).snapshot(campaign, published['run'])
    assert snap['input'] == original and snap['analysis'] == analyze(original)
    assert snap['superseded'] and snap['review'] is None
    state = repo.show(campaign)
    assert state['current_review']['id'] == review['decision']
    assert jobs.publish(job, token)['run'] == published['run']
    assert repo.show(campaign) == state
    with pytest.raises(Conflict):
        jobs.publish(job, 'another-token')
    with pytest.raises(Conflict):
        repo.review(campaign, published['run'], 'accept', 'Reviewer', 'Old work', 2)


def test_supplied_database_preserves_complete_runs_and_reuses_old_run(tmp_path, monkeypatch):
    incident = Path(__file__).resolve().parents[1] / 'examples' / 'correction-incident'
    ids = load(incident / 'identifiers.json')
    path = tmp_path / 'existing.db'
    shutil.copyfile(incident / 'study.db', path)
    repo, jobs = Repository(path), Jobs(path)
    before = repo.show(ids['campaign'])
    with sqlite3.connect(path) as db:
        stored = {run: loads(db.execute('SELECT result FROM runs WHERE id=?', (run,)).fetchone()[0])
                  for run in [ids['previous_run'], ids['current_run']]}
    # Historical reads must work without running the current engine at all.
    with monkeypatch.context() as patch:
        def unexpected_analysis(*args, **kwargs):
            pytest.fail('Snapshot recomputed a completed run')
        patch.setattr('truegate.engine.analyze', unexpected_analysis)
        for run, result in stored.items():
            snap = repo.snapshot(ids['campaign'], run)
            assert snap['analysis'] == result
            export(snap, tmp_path / run)
            assert verify(tmp_path / run)['verified']
    token = jobs.claim(ids['queued_job'], 'worker', 300)['token']
    jobs.compute(ids['queued_job'], token)
    published = jobs.publish(ids['queued_job'], token)
    assert published['run'] == ids['previous_run'] and published['reused']
    assert repo.show(ids['campaign'])['current_review'] == before['current_review']


def stage(ingest, campaign, data, delivery, revision, suffix=b''):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=HEADERS['readings'])
    writer.writeheader()
    writer.writerows(dict(r, revision=1) for r in data['records'])
    sources = {'readings': stream.getvalue().encode(),
               'transfer_history': dumps(data['transfer_history']).encode() + suffix}
    manifest = {'delivery_id': delivery, 'expected_revision': revision, 'sources': [
        dict(id=kind, kind=kind, sha256=hashlib.sha256(raw).hexdigest())
        for kind, raw in sources.items()]}
    session = ingest.open(campaign, manifest)['session']
    states = {kind: ingest.add(session, kind, raw) for kind, raw in reversed(list(sources.items()))}
    return session, states


def test_instrument_publication_binds_exact_bytes_and_rejects_unmatched_samples(tmp_path):
    path = tmp_path / 'ingest.db'
    repo, ingest = Repository(path), Ingestion(path)
    campaign = repo.create('Instrument corrections', 'screening')['campaign']
    original = evidence()
    session, _ = stage(ingest, campaign, original, 'initial', 0)
    assert ingest.publish(session)['revision'] == 1
    run = repo.run(campaign)['run']
    repo.review(campaign, run, 'accept', 'Reviewer', 'Initial delivery', 1)
    before = repo.snapshot(campaign, run)
    state = repo.show(campaign)
    invalid = correction(original)
    invalid['transfer_history']['bindings'][0]['record_id'] = 'absent-reading'
    session, states = stage(ingest, campaign, invalid, 'unmatched', 1)
    assert all(s['state'] == 'accepted' for s in states.values())
    for operation in [ingest.preview, ingest.publish]:
        with pytest.raises(WorkbenchError, match='existing sample'):
            operation(session)
    after = repo.show(campaign)
    assert after['datasets'] == state['datasets'] and after['current_review'] == state['current_review']
    assert ingest.show(session)['state'] == 'open'

    session, _ = stage(ingest, campaign, correction(original), 'legal', 1)
    assert ingest.publish(session)['revision'] == 2
    assert repo.show(campaign)['current_review'] is None
    run2 = repo.run(campaign)['run']
    repo.review(campaign, run2, 'accept', 'Reviewer', 'Legal correction', 2)
    # Identical parsed values with different original bytes are new evidence too.
    session, _ = stage(ingest, campaign, correction(original), 'reformatted', 2, b'\n  ')
    preview = ingest.preview(session)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE ingest_sources SET parsed='[]' WHERE session=?", (session,))
    assert ingest.preview(session) == preview
    assert ingest.publish(session)['revision'] == 3
    assert ingest.publish(session)['reused']
    assert repo.show(campaign)['current_review'] is None
    assert repo.snapshot(campaign, run) == dict(before, superseded=True)
    source = next(s for s in preview['input']['ingestion']['sources'] if s['kind'] == 'transfer_history')
    assert source['text'].endswith('\n  ')


def test_resolving_unknown_volume_cannot_clip_later_withdrawal(tmp_path):
    path = tmp_path / 'physical.db'
    repo, ingest = Repository(path), Ingestion(path)
    campaign = repo.create('Unknown delivery', 'screening')['campaign']
    original = evidence()
    event = original['transfer_history']['events'][0]
    event['status'] = 'unknown'
    del event['volume'], event['volume_unit']
    repo.import_data(campaign, original)
    run = repo.run(campaign)['run']
    repo.review(campaign, run, 'hold', 'Reviewer', 'Await measured volume', 1)
    before = repo.show(campaign)
    invalid = deepcopy(original)
    invalid['transfer_history']['events'].append(dict(event, revision=2, status='ok', volume=8, volume_unit='uL'))
    with pytest.raises(WorkbenchError, match='overdraws'):
        repo.import_data(campaign, invalid)
    assert repo.show(campaign) == before
    session, states = stage(ingest, campaign, invalid, 'invalid', 1)
    assert states['transfer_history']['state'] == 'rejected'
    assert 'overdraws' in states['transfer_history']['diagnostics'][0]['error']
    with pytest.raises(Conflict):
        ingest.publish(session)
    assert repo.show(campaign)['current_review'] == before['current_review']
    legal = deepcopy(invalid)
    legal['transfer_history']['events'][-1]['volume'] = 9
    session, states = stage(ingest, campaign, legal, 'legal', 1)
    assert all(s['state'] == 'accepted' for s in states.values())
    assert ingest.publish(session)['revision'] == 2
    assert repo.show(campaign)['current_review'] is None
    result = repo.run(campaign)['analysis']
    assert [o['dose_um'] for o in observations(result)] == pytest.approx([73, 73])


def test_expired_worker_cannot_publish_after_correction(tmp_path, monkeypatch):
    path = tmp_path / 'leases.db'
    repo, jobs = Repository(path), Jobs(path)
    campaign = repo.create('Lease fencing', 'screening')['campaign']
    original = evidence()
    repo.import_data(campaign, original)
    job = jobs.submit(campaign)['job']
    monkeypatch.setattr('truegate.jobs.time.time', lambda: 1000)
    first = jobs.claim(job, 'first', 10)
    jobs.compute(job, first['token'])
    repo.import_data(campaign, correction(original))
    monkeypatch.setattr('truegate.jobs.time.time', lambda: 1011)
    second = jobs.claim(job, 'replacement', 10)
    assert second['generation'] == first['generation'] + 1
    for operation in [jobs.compute, jobs.publish, jobs.heartbeat]:
        with pytest.raises(Conflict):
            operation(job, first['token'])
    with pytest.raises(Conflict, match='Compute'):
        jobs.publish(job, second['token'])
    jobs.compute(job, second['token'])
    result = jobs.publish(job, second['token'])
    assert repo.snapshot(campaign, result['run'])['analysis'] == analyze(original)
    monkeypatch.setattr('truegate.jobs.time.time', lambda: 2000)
    assert jobs.publish(job, second['token'])['run'] == result['run']
