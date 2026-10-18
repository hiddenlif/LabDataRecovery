Implemented complete-evidence dataset identity, dataset-pinned job reuse, codec-aware ingestion, lossless transfer reports, and atomic recovery that preserves historical results and reviews.

Validation: **68 tests passed**, including rollback, backup integrity, malformed evidence, and repeat safety.

Migration on a copy: **18 recovered, 12 unaffected, 10 blocked**. Original evidence remains unchanged.

See [recovery notes](/workspace/RECOVERY-NOTES.md), [executed report](/workspace/recovery-report/validation.json), and [rerunnable migration script](/workspace/scripts/recover_incident.py).
