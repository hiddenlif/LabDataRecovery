# Correction incident

All measurements and reviewer identities in this example are synthetic. The supplied database contains two immutable input revisions with complete analyses and reviews, plus a queued job pinned to the first revision. Both revisions produce 100 uM measurements; the transferred volume and selected operation revision differ. The database was populated through the documented repository and jobs APIs.

Run `PYTHONPATH=src python examples/correction-incident/reproduce.py /absolute/new/destination`. The script copies the supplied database before using it. It also starts a new study from the two JSON inputs. Inspect the printed states, job publication and historical reports. Preserve the supplied database and inputs as investigation evidence.
