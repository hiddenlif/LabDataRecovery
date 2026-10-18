# Operations

Use a new local SQLite file for a project. Keep the database and exported reports in a directory you control. No client data or credentials are included. Back up a database while the application is idle, or use SQLite's backup API; do not copy an actively changing database file without a consistent snapshot.

`truegate show --db PATH --campaign ID` lists imports, runs, decisions and events. Analysis failures are retained. Investigate a run left in `running` after a process interruption rather than editing its state blindly.

Commands emit one JSON result to standard output. User/data errors emit a JSON error to standard error and exit 2. A complete command returning zero is not a scientific approval; inspect its status and diagnostics.

Example report generation can be reproduced with `scripts/demo_reports.py`. All datasets in `examples/` are synthetic. Example reviewer labels are demonstration attribution and do not represent an actual quality approval.

The Docker image installs fixed dependency versions and runs as UID 10001. Mounted output directories need write permission for that UID. The build needs package-network access; normal analysis runs without network access. Validation receipts identify the actual tested platform. Do not infer support for an untested processor architecture.

Keep raw input revisions and analysis settings together when comparing outputs. Compare numeric values using method-appropriate tolerances rather than assuming identical floating-point bytes across BLAS implementations or processor architectures. Within one pinned runtime, ordering and seeded bootstrap operations are deterministic.

