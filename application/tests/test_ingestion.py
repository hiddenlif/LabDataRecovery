"""Regression coverage for durable delivery publication."""
import csv
import hashlib
import io
import sqlite3
import pytest
from truegate.examples import screening
from truegate.ingestion import Ingestion
from truegate.instrument_files import HEADERS
from truegate.repository import Repository
from truegate.errors import Conflict


def staged(tmp_path):
    path=tmp_path/'studies.db';repo=Repository(path);campaign=repo.create('Plate delivery','screening')['campaign']
    data=screening();sources={}
    for kind,rows in [('readings',[dict(r,revision=1) for r in data['records']]),('telemetry',data['telemetry'])]:
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=HEADERS[kind]);writer.writeheader();writer.writerows(rows)
        sources[kind]=stream.getvalue().encode()
    manifest={'delivery_id':'plate-delivery','expected_revision':0,'sources':[
        {'id':kind,'kind':kind,'sha256':hashlib.sha256(raw).hexdigest()} for kind,raw in sources.items()]}
    ingest=Ingestion(path);session=ingest.open(campaign,manifest)['session']
    return path,repo,campaign,ingest,session,sources


def test_incomplete_delivery_survives_reopen_and_duplicate_add(tmp_path):
    path,repo,campaign,ingest,session,sources=staged(tmp_path)
    assert ingest.add(session,'readings',b'truncated')['state']=='rejected'
    ingest.add(session,'readings',sources['readings'])
    with pytest.raises(Conflict):ingest.publish(session)
    resumed=Ingestion(path)
    assert resumed.add(session,'readings',sources['readings'])['reused']
    assert len(resumed.show(session)['attempts'])==2
    resumed.add(session,'telemetry',sources['telemetry'])
    publication=resumed.publish(session)
    assert resumed.publish(session)['dataset']==publication['dataset']
    assert len(repo.show(campaign)['datasets'])==1


def test_failed_session_transition_rolls_back_dataset_and_events(tmp_path):
    path,repo,campaign,ingest,session,sources=staged(tmp_path)
    for kind,raw in sources.items():ingest.add(session,kind,raw)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER stop_publish BEFORE UPDATE ON ingest_sessions WHEN NEW.state='published' BEGIN SELECT RAISE(ABORT,'interrupted'); END")
    with pytest.raises(sqlite3.IntegrityError):ingest.publish(session)
    state=repo.show(campaign)
    assert state['datasets']==[]
    assert not any(e['action'] in {'imported','ingest_published'} for e in state['events'])
    with sqlite3.connect(path) as db:db.execute('DROP TRIGGER stop_publish')
    assert ingest.publish(session)['revision']==1


def test_parsed_cache_is_not_the_evidence_source(tmp_path):
    path,repo,campaign,ingest,session,sources=staged(tmp_path)
    for kind,raw in sources.items():ingest.add(session,kind,raw)
    before=ingest.preview(session)
    with sqlite3.connect(path) as db:db.execute("UPDATE ingest_sources SET parsed='[]'")
    assert ingest.preview(session)==before
