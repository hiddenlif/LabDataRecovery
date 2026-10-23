"""Investigate correction behavior in a fresh study and a copied existing study."""
import json
from pathlib import Path
import shutil
import sys
from truegate.repository import Repository
from truegate.jobs import Jobs
from truegate.reporting import export
from truegate.errors import WorkbenchError
HERE=Path(__file__).resolve().parent

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    ids=json.loads((HERE/'identifiers.json').read_text())
    shutil.copyfile(HERE/'study.db',out/'existing.db')
    repo=Repository(out/'existing.db');jobs=Jobs(out/'existing.db')
    output={'existing_current_revision':repo.show(ids['campaign'])['current_revision']}
    for name,key in [('previous','previous_run'),('current','current_run')]:
        snap=repo.snapshot(ids['campaign'],ids[key]);export(snap,out/name)
        output[name+'_bindings']=snap['analysis']['result']['transfer_history'][0]['bindings']
    lease=jobs.claim(ids['queued_job'],'example-worker',300)
    try:
        jobs.compute(ids['queued_job'],lease['token'])
        output['old_job']=jobs.publish(ids['queued_job'],lease['token'])
    except WorkbenchError as error:
        output['old_job_error']=str(error)
    fresh=Repository(out/'fresh.db');campaign=fresh.create('Fresh correction reproduction','screening')['campaign']
    output['first_import']=fresh.import_data(campaign,json.loads((HERE/'initial.json').read_text()))
    run=fresh.run(campaign)['run'];fresh.review(campaign,run,'accept','Example reviewer','First revision inspected',1)
    output['correction_import']=fresh.import_data(campaign,json.loads((HERE/'corrected.json').read_text()))
    output['fresh_current_review']=fresh.show(campaign)['current_review']
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
