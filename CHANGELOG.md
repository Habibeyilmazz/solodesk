# Changelog

All notable changes to solodesk are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Found by cloning the repository fresh and following the README, then reading the code.

### Fixed

- Changing the password now ends every open session. A cookie issued under the example
  password used to stay valid for 14 days after the password was changed. Upgrading signs
  everyone out once.
- `make run`, `make dev` and `make seed` no longer run `.env` through the shell. A password
  with spaces was silently dropped ("Set SOLODESK_PASSWORD..." although it was set) and one
  containing `&` or `;` executed the rest of the line.
- The PDF of a sent invoice keeps the client and business details it was sent with; editing
  a client or the settings later no longer rewrites it. Invoices sent before this change have
  no stored copy and still print current details.
- The invoice prefix field in Settings validates in the browser again (its `pattern` was not
  a valid regular expression, so browsers ignored it).

### Changed

- CI signs in to the Docker container, downloads an invoice PDF, checks that `TZ` takes
  effect and runs the backup commands from the README.
- README: how to change the password, quoting in `.env`, `PYTHON=` for older systems, Docker
  upgrades and backups, the shared login lockout behind Docker, the PDF font's limits.
- The empty dashboard points to Settings for the invoice header details.
- Removed unused re-exports from `db.py`.

### Checked, no change needed

- The invoice PDF opens in Chromium's built-in viewer and in macOS Quick Look, including a
  ten-page invoice with long Turkish text.
- The Docker image contains the PDF fonts and the time zone database (now asserted in CI).

## [0.1.0] - 2026-11-21

First release.

### Added

- Clients (with invoice currency: TRY, USD, EUR, GBP) and projects (hourly rate, archive flag).
- Time tracking: start/stop timer available on every page, manual entries, billable flag.
- Invoices from unbilled tracked time (one line per project), fixed line items, or both, with
  percentage discount and tax. Drafts are editable; sent invoices are locked.
- Sequential invoice numbers assigned when an invoice is marked sent; configurable prefix.
- Status flow draft, sent, paid; overdue derived from the due date; payment can be undone.
- PDF export (fpdf2 with bundled DejaVu Sans) and CSV export of invoices and time entries.
- Dashboard: revenue per month, unpaid and overdue totals, hours this week, top clients.
- Single-user auth: scrypt password hash, hashed server-side sessions, HttpOnly SameSite=Strict
  cookie, CSRF token on writes, login rate limit, security headers.
- Demo data (`make seed`), Makefile (`make dev`, `make run`), Dockerfile and compose file.
- Tests: pytest API and unit tests, Node unit tests for the money and duration parsers,
  two Playwright specs (the main flow, then edits and undo paths), and a CI workflow that also builds and boots the Docker image.

### Notes for whoever works on this next

- Money is integer minor units everywhere; quantities are hundredths; rates are basis points.
  `backend/solodesk/money.py` and `frontend/src/lib/money.ts` must stay in step (both are tested).
- There are no schema migrations. Tables are created on start, so a brand-new table (like
  `IssuedCopy`) reaches existing databases by itself, but adding or changing a column on an
  existing table does not: that needs a migration story first (see Roadmap in the README).
- `IssuedCopy` stores the `Client` and `Settings` rows as JSON and `parties()` in
  `routers/invoices.py` reads them back without validation. A new field on either model must
  have a default, or old copies will lack it when the PDF is drawn.
- Session cookies are stored as an HMAC keyed with `Config.session_key`, which `from_env`
  derives from the password. Anything that builds a `Config` by hand must pass a key.
- The Makefile reads `.env` with `dotenv run` (python-dotenv, in the `dev` extra); Docker
  Compose reads the same file with its own parser. Single-quoted values mean the same in both.
- Every database transaction starts with `BEGIN IMMEDIATE` (`db.py`), so requests run one at a
  time and check-then-write rules cannot race. Keep that if you touch the engine setup.
- The login rate limiter lives in process memory (see the `shortcut:` comment in `auth.py`).
- `overdue` is never stored; it is computed from `status == "sent"` and the due date.
- Screenshots in `docs/screenshots` come from `frontend/scripts/screenshots.mjs` run against a
  seeded instance.
- Default ports: 4150 (app), 4151 (Vite dev server), 4152 (Playwright smoke test).
