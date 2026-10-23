"""Run the persisted study through correction, a pinned job and historical export."""
import json
from pathlib import Path
import shutil
import sys
from truegate.codec import load
from truegate.jobs import Jobs
from truegate.repository import Repository
from truegate.reporting import export

HERE = Path(__file__).resolve().parent


def main():
    destination = Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(HERE/'study.db',destination/'study.db')
    repo=Repository(destination/'study.db');jobs=Jobs(destination/'study.db')
    ids=load(HERE/'study-identifiers.json');campaign=ids['campaign']
    pinned=jobs.submit(campaign)['job']
    token=jobs.claim(pinned,'walkthrough',60)['token']
    correction=repo.import_data(campaign,load(HERE/'corrected.json'))
    jobs.compute(pinned,token);old=jobs.publish(pinned,token)['run']
    current=repo.run(campaign)['run']
    old_snapshot=repo.snapshot(campaign,old);new_snapshot=repo.snapshot(campaign,current)
    export(old_snapshot,destination/'pinned-report')
    export(new_snapshot,destination/'corrected-report')
    def doses(s):
        return {b['record_id']:b['dose_um'] for h in s['analysis']['result']['transfer_history'] for b in h['bindings']}
    print(json.dumps({'revision':correction['revision'],'pinned_job_doses':doses(old_snapshot),
                      'corrected_doses':doses(new_snapshot),'pinned_is_historical':old_snapshot['superseded'],
                      'reports':[str(destination/'pinned-report'),str(destination/'corrected-report')]},indent=2))


if __name__=='__main__':main()
