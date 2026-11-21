# Changelog

All notable changes to solodesk are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
  a Playwright smoke test, and a CI workflow that also builds and boots the Docker image.

### Notes for whoever works on this next

- Money is integer minor units everywhere; quantities are hundredths; rates are basis points.
  `backend/solodesk/money.py` and `frontend/src/lib/money.ts` must stay in step (both are tested).
- There are no schema migrations. Tables are created on first start; changing a model means
  adding a migration story first (see Roadmap in the README).
- The login rate limiter lives in process memory (see the `shortcut:` comment in `auth.py`).
- `overdue` is never stored; it is computed from `status == "sent"` and the due date.
- Screenshots in `docs/screenshots` come from `frontend/scripts/screenshots.mjs` run against a
  seeded instance.
- Default ports: 4150 (app), 4151 (Vite dev server), 4152 (Playwright smoke test).
