# Recoverable instrument deliveries

A delivery is a complete screening revision assembled from independently arriving readings and dispensing CSVs. It does not merge silently with the previous dataset. Use a new delivery ID for a correction to published evidence. Existing JSON import, analysis, durable jobs, reviews and exports remain available.

## Commands

All commands return one JSON object. Contract errors exit 2 with a JSON error on stderr. `ingest-add` returns exit 0 for a durably recorded rejected source; inspect its `state` and `diagnostics`.

```
truegate ingest-open --db studies.db --campaign CAMPAIGN manifest.json
truegate ingest-add --db studies.db --session SESSION --source readings readings.csv
truegate ingest-show --db studies.db --session SESSION
truegate ingest-preview --db studies.db --session SESSION
truegate ingest-publish --db studies.db --session SESSION
truegate ingest-cancel --db studies.db --session SESSION
```

The manifest contains `delivery_id`, nonnegative integer `expected_revision` (0 for an empty campaign), and a nonempty `sources` array. Each source has a unique trimmed `id`, `kind` (`readings` or `telemetry`), and lowercase SHA-256 of the exact file bytes. At least one readings source is required. Source-list order is immaterial; all other manifest content is bound. Opening the same delivery ID and manifest again returns the same session. Reusing that ID with different content is an error. A new session requires the expected current campaign revision and a screening campaign.

## Interchange files

UTF-8 CSV accepts an optional BOM, quoted fields, LF or CRLF, and arbitrary column order. Headers must be unique and match the following sets exactly. Text fields are stripped. Numeric fields must be finite. CSV revisions are exact integers from 1 to 9223372036854775807, including integral decimal or scientific notation. Files are limited to 20 MiB each.

Readings headers: `id,plate,well,revision,assay,role,signal,compound,dose,dose_unit`.

Each row follows the screening record contract. Control rows leave compound/dose/unit empty. Sample concentrations use the existing concentration units. Readings revisions describe corrected measurements of one physical `(plate,well)`; they are separate from dispensing revisions.

Telemetry headers: `plate,well,revision,status,actual_dose,dose_unit`.

Status is `ok`, `failed`, or `cancelled`. Successful transfers require finite concentration values in supported units. Other statuses leave actual dose/unit empty. Existing transfer reconciliation defines exclusions for failed, cancelled, missing or zero-dose transfers. Negative concentrations are rejected.

Malformed rows reject the entire source, with physical CSV line diagnostics; no partial records are published. A fingerprint mismatch is a rejected attempt and may be retried with the declared bytes. An accepted source cannot be replaced. Repeating identical accepted bytes is idempotent and adds no attempt. Undeclared sources are errors. Show exposes source states and ordered attempts after reopening the application.

## Resolution and transactions

Preview and publish require every declared source accepted. Resolve original stored bytes again and check their fingerprints. An altered parsed cache must not change the result. For each readings `(plate,well,revision)`, identical normalized records merge provenance; conflicting content is an error even for a superseded revision. Select the highest readings revision per well, independently of file arrival order. Final IDs must be unique. A plate has one assay. Telemetry revisions use the same exact-duplicate/conflict rule; retain all distinct revisions and let the existing dispensing rules select the latest. Telemetry must reference a sample well in the resolved readings.

Preview returns `input`, `input_sha256`, and `base_current`, without importing or analyzing. The normalized input contains `ingestion.manifest`, `ingestion.sources` (`id`, `kind`, `sha256`, exact UTF-8 `text`, including any BOM), and `ingestion.record_lineage` (`record`, `plate`, `well`, `reading_revision`, and contributing `sources` with source ID and CSV line). Canonical results are independent of arrival order. Source text re-encoded as UTF-8 must reproduce the declared fingerprint.

Publish checks the current campaign revision against the manifest and commits dataset creation, import event, session state and publication event in one transaction. Concurrent deliveries against the same revision have at most one winner. A failure at any point leaves no partial publication, and retry can succeed. Repeating a completed publication returns its original dataset even after later imports. Cancellation preserves staging evidence, is idempotent, and prevents further adding, previewing or publishing. Published evidence cannot be cancelled.

Published input flows through synchronous analysis, leased jobs and historical report export without losing source text or lineage. The report displays instrument source lineage and the delivery manifest; its snapshot retains the exact source evidence. New input invalidates current-review eligibility without rewriting old analyses or reports. Migrating an existing database preserves its datasets, jobs, results and decisions.

## Persistence compatibility

The additive SQLite schema is version 4. Operational tooling inspects `ingest_sessions` (id, campaign, delivery_key, manifest, manifest_sha, expected_revision, state, published_dataset, created), `ingest_sources` (session, source_id, state, raw, sha, parsed, diagnostics), and `ingest_attempts` (sequence, session, source_id, sha, state, diagnostics). `raw` stores original BLOB bytes; manifest, parsed and diagnostics are JSON text. `parsed` is a disposable cache. Source states are pending, accepted or rejected; session states are open, published or cancelled. `(campaign,delivery_key)` and `(session,source_id)` are unique. Attempts append in sequence order; accepted replays add no attempt. Retain foreign-key integrity and the existing datasets, runs, jobs, decisions and events interfaces. Publication adds one `imported` event and one `ingest_published` event. Transition failures must roll back both events and dataset creation. Schema upgrades must preserve existing records.
