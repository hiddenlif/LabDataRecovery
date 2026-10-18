Implemented full evidence identity, dataset-pinned job reuse, complete transfer exports, and transactional recovery.

Validation: **64 tests passed**. Migration recovered **18 studies**, left **12 unaffected**, and blocked **10**. Historical results and reviews were preserved; backups and repeat safety verified. Supplied evidence remains untouched.

- [Changes and blocked-study explanations](/workspace/RECOVERY-NOTES.md)
- [Executable migration](/workspace/scripts/recover_incident.py)
- [Executed migration report](/workspace/recovery-artifacts/apply.json)
