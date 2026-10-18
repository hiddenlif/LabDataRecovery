# Architecture

The command-line interface delegates validation, analysis, storage and reporting to separate modules.

* `codec`: strict JSON, canonical serialization and fingerprints.
* `schema`, `units`, `policy`: input fields, compatible measurements and analysis settings.
* `calibration`, `plates`, `curves`, `screening`: dispensing history, plate QC, response fitting and evidence assembly.
* `bridge`, `stability`, `counts`: study-specific estimators and diagnostics.
* `engine`: common dispatch and analysis envelope.
* `database`, `repository`: schema migrations, transactional input revisions, runs and review events.
* `reporting`: HTML, CSV, complete snapshots and integrity verification.
* `examples`: deterministic synthetic study generation.

## Data lifecycle

A campaign has one study kind and many immutable input revisions. An analysis is bound to one dataset revision, a fully resolved policy fingerprint, and an engine version. Identical completed analyses are reusable only within that exact identity. Failed analyses retain their error and can be retried. A synchronous `run` that exits while marked running still needs operator investigation. For recoverable worker execution, use the separate durable job protocol in [analysis jobs](analysis-jobs.md), which stages results before publishing them into the same run and review history.

Data validation and analysis consume the same input representation in direct and stored execution. A completed analysis does not become current merely because it finishes later: currentness follows the latest imported dataset revision.

Reviews append decisions; they do not overwrite history. The reviewer supplies the revision they inspected. A review of an old input revision is rejected. After a new import, prior decisions remain visible in history but are not current decisions. Different analysis policies on the current data retain separate reviews.

Exports acquire their campaign, input, result and review in one database transaction. Historical exports are allowed and visibly marked when superseded. Exported review records are snapshots, not live links. Re-exporting after another review creates a different review snapshot. Existing report destinations are preserved rather than overwritten.

SQLite transactions serialize changes. Foreign keys prevent orphan records. Database initialization is additive and idempotent. A database from a newer schema version is rejected. Local file access is the security boundary; this release is not a multi-user service.


Instrument deliveries use `instrument_files` for strict CSV adapters, `ingest_resolution` for deterministic reconciliation, and `ingestion` for persisted source state and atomic publication into the existing repository. Original source bytes remain bound to the resulting dataset.

Calibration graphs resolve shared log-scale error sources before channel fitting. `uncertainty` computes first-order sensitivities using the fitted response Jacobian. Screening decisions consume propagated intervals; repository and job fingerprints bind the complete input graph. The numerical contract states the local approximation and its limits.

Physical dispensing reconstruction is specified in [transfer history](transfer-history.md). Its initial contents, operation revisions and measurement boundaries are input evidence, shared by direct analysis, imports, jobs and reports.
