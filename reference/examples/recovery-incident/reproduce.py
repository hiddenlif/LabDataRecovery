"""Surface an intake discrepancy without modifying the supplied evidence."""
from pathlib import Path
import json
import shutil
import sqlite3
import sys
from truegate.recovery import recover
HERE=Path(__file__).resolve().parent

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    path=out/'study.db';shutil.copyfile(HERE/'study.db',path)
    cid=json.loads((HERE/'example.json').read_text())['campaign']
    with sqlite3.connect(path) as db:
        datasets=db.execute('SELECT COUNT(*) FROM datasets WHERE campaign=?',(cid,)).fetchone()[0]
        deliveries=db.execute("SELECT COUNT(*) FROM ingest_sessions WHERE campaign=? AND state='published'",(cid,)).fetchone()[0]
        links=[r[0] for r in db.execute("SELECT published_dataset FROM ingest_sessions WHERE campaign=? AND state='published' ORDER BY id",(cid,))]
    report=recover(path,dry_run=True)
    print(json.dumps({'campaign':cid,'published_deliveries':deliveries,'stored_datasets':datasets,
                      'distinct_linked_datasets':len(set(links)),
                      'recovery_preview':next(e for e in report['studies'] if e['campaign']==cid)},indent=2))

if __name__=='__main__':main()
