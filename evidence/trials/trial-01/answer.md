Implemented full-evidence dataset identity, dataset-bound job reuse, codec-aware ingestion, complete report rows, and atomic, repeat-safe recovery.

Validation: **64 tests passed**. Recovery on a database copy repaired **18 studies**, left **12 unaffected**, and safely blocked **10**. All **40 runs and 40 review decisions** were preserved.

Details and blocked-study explanations: [RECOVERY-NOTES.md](/workspace/RECOVERY-NOTES.md). Reproducible migration: [script](/workspace/scripts/recover_incident.py), [executed validation](/workspace/recovery-report/validation.json).
