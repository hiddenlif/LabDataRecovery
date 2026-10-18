# Recovery ledger interoperability

The append-only journal is the durable ordering authority. Display timestamps can come from different workers. Dataset revisions allocate storage and concurrency tokens.

`transfer_evidence_recovered_preview` records a partial recovery, not a completed reconciliation. Payload version `transfer-evidence-preview-0` contains `sessions` with `session`, `from_dataset`, `to_dataset`, `sha256` and `jobs` with `job`, `from_dataset`, `to_dataset`. Appended datasets carry the complete normalized input. Publication pointers may still be original. The preview tool could pin waiting work to its last appended dataset. Adopt only verifiable matching revisions and preserve this audit record. Mismatching provenance is not permission to guess.

A completed recovery may record `current_dataset` in its event. Current selection uses that evidence until a subsequent ordinary import advances the study. Already produced results remain attached to their original dataset. Historical acceptance must not transfer to different evidence.
