# TrueGate Hit Review Workbench

A local scientific application for screening panels, paired assay comparisons, batch stability studies, and rare-event qualification. It keeps imported study revisions, analysis settings, review decisions, and exported reports connected.

Research software for reproducible scientific analysis and review. Included studies are synthetic demonstrations. Development is AI-assisted and backed by executable checks. The application is not a validated laboratory system or a clinical decision tool.

## Run an example

Requires Python 3.12 or newer. The lock file records the development environment.

```sh
uv sync --frozen
uv run truegate analyze examples/screening.json --output screening-result.json
uv run pytest
```

To record a study and produce an HTML report:

```sh
uv run truegate create --db studies.db --name "Screening pilot" --kind screening
# Use the campaign identifier returned above in the following commands.
uv run truegate import --db studies.db --campaign CAMPAIGN examples/screening.json
uv run truegate run --db studies.db --campaign CAMPAIGN
# Use the returned run identifier.
uv run truegate review --db studies.db --campaign CAMPAIGN --run RUN --revision 1 --action hold --reviewer "Your name" --note "Review orthogonal evidence"
uv run truegate export --db studies.db --campaign CAMPAIGN --run RUN --directory reports/pilot
uv run truegate verify-report reports/pilot
```

Open `reports/pilot/index.html`. Reports include the full input and analysis snapshot, a summary CSV, and file fingerprints. Review names are user-entered attribution, not authenticated electronic signatures.

## Four study workflows

* **Screening:** reconcile dispensing records, check controls, normalize plates, fit each assay channel, and combine supporting and conflicting evidence.
* **Method comparison:** match donor/sample pairs across methods and estimate a donor-weighted ratio with a cluster bootstrap interval.
* **Stability:** fit batch-specific weighted trends and find the first confidence-bound crossing within the documented observation window.
* **Rare events:** subtract batch-matched background, retain uncertainty from both measurements, and identify a candidate quantification range.

Read [data formats](docs/data-formats.md), [scientific methods](docs/scientific-methods.md), [architecture](docs/architecture.md), and [operations](docs/operations.md) before using your own measurements. All settings in the examples are study assumptions rather than universal acceptance limits.

## Docker

```sh
docker build -t truegate-workbench .
docker run --rm --network none truegate-workbench analyze /app/examples/screening.json
```

Mount a writable directory at `/data` to retain a database or report. The application runs as an unprivileged user. See the operations guide for ownership and platform notes.

## Scope

The current application is a command-line tool with portable HTML reports. It does not connect to instruments, provide multi-user authentication, manage electronic signatures, or authorize material disposition. Fits assume the models described in the methods document. Poorly identified or unbracketed curves are reported explicitly rather than assigned a confident potency.


## Campaign reconciliation and durable workers

See [campaign identity](docs/campaign-identity.md) to combine independently named screening studies without mixing wells or entities, and [analysis jobs](docs/analysis-jobs.md) to submit, lease, compute and publish recoverable analyses.

## Instrument evidence

Recoverable instrument delivery staging and atomic publication are described in [the ingestion contract](docs/ingestion.md). [Shared calibration uncertainty](docs/calibration-uncertainty.md) connects dilution ancestry to screening intervals, review and historical reports. Synthetic examples are in `examples/instrument-delivery` and `examples/calibration`.

## Physical transfer histories

[Transfer reconstruction](docs/transfer-history.md) tracks actual liquid additions, corrections and measurement-time contents. Run `PYTHONPATH=src python examples/transfer-history/reproduce.py /absolute/new-directory` to exercise a persisted study, a correction, a pinned worker and two reports.

Use [retained-delivery recovery](docs/evidence-recovery.md) to inspect and repair synthetic suppressed delivery histories. The [recovery example](examples/recovery-incident/README.md) uses copies of a supplied study. Dry-run is read-only; applying requires a new backup destination.
