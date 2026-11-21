# Changelog

All notable changes to solodesk are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security (round 11, security lens)

Reviewed the whole repo by hand, then with a read-only Codex review; every fix was reproduced
against a running server first and has a regression test in `tests/test_auth.py`.

- Unauthenticated memory exhaustion: FastAPI reads and parses the whole request body before
  it checks the session, so one 400 MB POST without a cookie raised the server's memory from
  117 MB to 520 MB, and it stayed there. Parsed JSON costs about 25 times its size, and a
  body with many unknown keys answers with one 422 error per key (Codex: a 539 KB login body
  cost 67 MB). Bodies are now refused with 413 before they are read: 16 KB without a valid
  session, 32 MB with one (a full 5,000,000-character Toggl import fits). Chunked bodies are
  counted as they arrive. This replaces round 3's "no request body size limit, accepted".
- `/api/docs` loaded Swagger UI as `swagger-ui-dist@5` from jsDelivr, so whatever 5.x was
  published last ran on the app's own origin, where it can read the CSRF token and act as
  you. It is now pinned to 5.34.1 with SRI hashes (checked against the npm tarball and the
  CDN copy; the page renders all 33 operations in Chromium). The favicon no longer comes from
  fastapi.tiangolo.com.
- CI now runs `pip-audit` on the installed Python dependencies next to `npm audit`.
- Checked and fine: `npm audit` and `pip-audit` report nothing; git history has no secrets or
  databases and only the noreply identity; CI has `contents: read`, SHA-pinned actions and no
  persisted token; the container runs as a non-root user and compose binds to 127.0.0.1; SQL
  is SQLModel expressions only; no outbound requests (no SSRF); CSV cells are formula-escaped;
  PDF and CSV filenames are built from validated characters; React renders all text escaped.
- Not done: Python dependencies and Docker base images are not pinned (no lock file, tags not
  digests), so builds take the newest compatible versions. Reported gaps unchanged: Toggl
  parser untested on a real export; credit notes, voided-on date and homepage not done.

### Changed (round 10, design lens)

Screenshotted every page of the running app (seeded and empty database) at 1280 px and
390 px, light and dark, and tabbed through the dashboard with the keyboard. The look holds
up; three things were off and are fixed:

- Time page: each day is its own table, so the description, tag and duration columns started
  at a different place every day. Day tables now share fixed column widths (above 600 px).
- Dashboard on phones: client names in "Top clients" wrapped to three lines next to a short
  bar, and the per-day hour labels ("4h 30m") wrapped. Name and amount now sit on one line
  with the bar full width underneath, and the hour labels stay on one line.
- Time page on a fresh install showed three empty notes and a "Show 30 more days" button.
  With no projects at all, only the "add a client and a project" note remains.
- Checked and fine, so left alone: every focusable element shows a focus ring in both
  themes, transitions sit behind `prefers-reduced-motion: no-preference`, pages load in a
  few ms locally so there is no loading spinner to flash. README screenshots refreshed.
- Reported gaps re-checked: the 10,000-hour draft cap and 5,000-entry Time list cap are
  limits a freelancer will not reach, not bugs; Toggl parser still untested on a real
  export; credit notes, voided-on date and homepage still not done.
- `make test` (78 pytest, 11 unit) and `make e2e` (5 tests) pass locally.

### Fixed (round 9, first-run lens)

Followed the README quickstart literally in a fresh clone (`make seed`, `make run`, sign in,
every page, an invoice PDF, `/api/docs`, an empty database, a Toggl import): it all worked.
Then reviewed the code, with a Codex second opinion; each fix has a test that failed first.

- After a Toggl import the Time page still listed only the last 30 days, so importing older
  history (the usual case) looked like it had added nothing until you pressed "Show 30 more
  days" many times. The import now returns `earliest_date` and the page widens its range to
  it (`tests/test_import.py`, `src/lib/time.test.ts`, `e2e/4-import.spec.ts`).
- Adding time to a draft summed two rounded quantities on a project's line, so two 1-minute
  entries billed 0.04 h instead of 0.03 h. The line's minutes are now rounded once, as for a
  new draft; a quantity edited by hand still just gets the new hours added.
- Deleting a project named on an invoice line (possible after voiding the invoice and deleting
  the released time) answered 500. It is now a 409 asking to archive the project.
- README: CI runs on pushes to `main` and on pull requests, not on every push.
- Seen and left alone: a draft built from more than about 10,000 hours of one project cannot
  be re-saved (quantity cap), and the Time page shows at most 5,000 entries per range. The
  Toggl parser is still untested on a real account export; voided-on date, partial credit
  notes, social preview and homepage remain undone (features, not bugs).

### Changed (round 8, performance and accessibility lens)

Measured first, on a database with 200 clients, 600 projects, 30,000 time entries and 5,000
invoices (25,000 lines), on a laptop, Chromium via Playwright.

- Built files under `/assets` were sent uncompressed and without a cache header, so every
  visit re-validated them. They are now gzip-compressed (only there, not API responses, which
  carry the CSRF token) and cached for a year as immutable (file names carry a content hash).
  Over the wire: JS 306,464 B to 92,948 B, CSS 19,365 B to 5,107 B. Test in `tests/test_auth.py`.
- Accessibility: axe-core 4.10 over every page and an invoice, light and dark, found one
  failure, the draft status stamp (colour contrast 4.2:1, caused by the stamp's opacity).
  Removed the opacity; axe now reports no violations on all of those views.
- Measured and fine, so left alone: list, dashboard and CSV endpoints answer in 2 to 8 ms on
  the large database, a PDF in about 55 ms, start-up is about 0.5 s, first contentful paint
  76 ms locally, one font file (latin subset) is fetched. Every dependency is imported and
  used, so nothing was removed. The Toggl-export, voided-on, partial credit note, social
  preview and homepage gaps are unchanged (features or web-only settings, not bugs).
- `make test` (76 pytest, 10 unit), `make lint` and `make e2e` (5 tests) pass locally.

### Added (round 7, feature lens)

- Import time from a Toggl Track detailed report (CSV). **Import from Toggl** on the Time page
  shows a preview first (a dry run: entries, hours, clients and projects it would create),
  then imports. Clients and projects are matched by name ignoring case and created when
  missing (new clients get the currency picked in the dialog, new projects a rate of 0).
  Entries already present with the same project, date, minutes and description are skipped,
  so re-importing is safe. All or nothing, with row numbers in the error. API:
  `POST /api/import/toggl` with `{"csv": "...", "currency": "EUR", "dry_run": true}`.
  Tests in `tests/test_import.py` and `e2e/4-import.spec.ts`.
- Chosen by using the app: switching from another tracker meant retyping history by hand.
  Only Toggl's detailed report is read (columns Client, Project, Description, Billable,
  Start date in YYYY-MM-DD, Duration as HH:MM:SS); Clockify and Harvest exports are not.
  The parser was written against Toggl's documented column names, not a real account export.
- Add tracked time to an existing draft (**Add tracked time** on the draft editor). Before,
  hours logged after a draft was made could only be billed by deleting the draft and starting
  over. Hours for a project already on the draft are added to its line, and the line's date
  span is refreshed unless its description was edited; other projects get a new line. Unsaved
  edits are saved first. API: `POST /api/invoices/{id}/time` with `{"time_entry_ids": [...]}`.
  Tests in `tests/test_invoices.py` and `e2e/4-import.spec.ts`.
- Reported gaps re-checked: no social-preview image (still a web-only upload), no voided-on
  date, no partial credit notes, no homepage and an issue-based security contact remain as
  they were; none is a bug.
- Ran `make test` (75 pytest, 10 unit), `make lint` and `make e2e` (5 tests) locally: green.

### Added (round 6, launch lens)

- `docs/demo.gif`, recorded from the real app by `frontend/scripts/demo.mjs` (Playwright plus
  ffmpeg), at the top of the README. README gained an honest comparison with Invoice Ninja,
  Kimai, Crater, spreadsheets and hosted tools, and a Contributing section.
- `CONTRIBUTING.md`, bug and feature issue templates. Repo topics extended.
- Reran `make test` (68 pytest, 10 unit) and `make e2e` (3 specs) locally: all green.
- Not done: no hero or social-preview image (GitHub only accepts that upload through the web
  settings); voided-on date and partial credit notes still undone.

### Fixed (round 5, reliability lens)

Found by feeding the API odd input; each has a failing test first.

- An invoice issue date of 9999-12-31 (issue date plus payment terms overflows Python's dates)
  answered 500. Dates on invoices, time entries and `paid_on` must now be within 1970-2100,
  otherwise 422 (`tests/test_invoices.py`).
- A lone surrogate in JSON text (valid JSON, not valid UTF-8) answered 500 on login and on every
  text field, and an id beyond SQLite's 64-bit range (for example `client_id` 10^30) answered
  500. Both are now 422. Validation errors no longer echo the offending input back
  (`tests/test_clients_time.py`).
- Probed and fine: Unicode, emoji, CJK and right-to-left text in PDFs (glyphs DejaVu lacks are
  skipped, not an error), 500-character unbroken words, 200 lines at maximum price (total stays
  below 2^53), malformed and non-object JSON, negative or non-numeric limits.
- The previous round's reported gaps (no voided-on date, no partial credit notes) are features,
  not bugs, and remain undone; a voided-on date needs a migration mechanism first.

### Added (round 4, feature lens)

- Void a sent or overdue invoice. Before, a sent invoice with a mistake had no way out: it
  stayed unpaid and overdue on the dashboard forever and its hours could never be billed
  again. Now **Void invoice** (with a confirmation) keeps the number and lines, shows a Void
  stamp, a Void filter on Invoices and `void` in the CSV, prints "VOID: not payable" on the
  PDF, drops the invoice from unpaid, overdue and revenue figures, and releases its tracked
  time so a corrected invoice can be made from it. Void is final; a paid invoice must be
  marked unpaid first. API: `POST /api/invoices/{id}/status` with `{"status": "void"}`.
  No schema change (status is a text column). Tests in `tests/test_invoices.py`,
  `tests/test_reports.py` and `e2e/2-housekeeping.spec.ts`.
- Not done: no date is stored for when an invoice was voided (it would need a new column, and
  there are no migrations yet), and there are no partial credit notes.

### Checked, no change needed (round 4)

- Reported gaps re-checked: the missing request body size limit is a documented, accepted
  limit for a localhost app behind a proxy, not a bug; tables below ~360px still scroll, as
  the README's roadmap says.

### Security (round 3, security lens)

- Login guessing is now capped across all addresses together: 50 failures per 15 minutes,
  on top of the 5 per address. Before, uvicorn's default trust of `X-Forwarded-For` from
  127.0.0.1 let any local process, or a web page that DNS-rebinds to localhost, rotate that
  header and guess without limit (reproduced against a running instance; regression tests in
  `tests/test_auth.py`). The trade-off, documented in the README: a sustained attack also
  keeps the owner out until it stops.
- CI pins every action to a commit SHA, checks out without persisting the token, and runs
  `npm audit --audit-level=high`.

### Checked, no change needed (round 3)

- `npm audit` and `pip-audit` (against the installed backend dependencies): no known
  vulnerabilities. Git history holds no secrets, `.env` or database files; commits use only
  the noreply identity.
- SQL is built with SQLModel expressions only; the SPA fallback refuses paths outside the
  build folder; CSV cells are formula-escaped; React renders all user text escaped; no
  outbound requests exist (no SSRF surface); the PDF filename only contains the validated
  prefix characters.
- Known and accepted: no request body size limit (put a reverse proxy in front before
  exposing it), Swagger UI at `/api/docs` loads its assets from a CDN without a CSP.

### Added (round 2, design lens)

- Dark mode that follows the system setting. Colours are tokens on `:root` in
  `frontend/src/styles.css`, redefined in one `prefers-color-scheme: dark` block; the navy
  cover stays navy, native date pickers and selects follow via `color-scheme`.
- Phone layout (600px and below) for the invoice list, the time log, the unbilled-time picker
  on a new invoice and the draft line editor: each row becomes a small stacked grid (class
  `stacks` plus per-table grid areas), so status, totals and Edit are on screen without
  scrolling sideways. A third Playwright spec, `e2e/3-phone.spec.ts`, checks every page at
  390px fits the width and the invoice row is fully visible (it fails on the old CSS).
- README screenshots now include dark mode and the phone invoice list
  (`frontend/scripts/screenshots.mjs` takes them).

### Fixed (round 2)

- On phones, tables no longer stop short of their box (the old `display: block` scroll hack
  shrank them); project names and top-client names wrap instead of pushing amounts off screen.
- The status filter on Invoices no longer wraps into a broken second row on phones.
- The invoice stamp and page titles are smaller on phones so "Invoice INV-0047" fits one line.
- The keyboard focus ring on sidebar links is drawn inside the sidebar instead of past its edge.

Found by cloning the repository fresh and following the README, then reading the code.

### Fixed

- `make` with a Python older than 3.12 (macOS ships 3.9) now stops with a clear message.
  Before, pip failed with an unrelated error about `setup.py` and left a half-made `.venv`,
  so the README's own fix, `make run PYTHON=python3.12`, then failed with
  "dotenv: No such file". A failed install now removes the venv. Plain `make` runs the app.
- A deleted draft's id is no longer handed to the next invoice. A second tab still showing
  the deleted draft could save into the new, unrelated invoice and replace its lines. The
  same applies to clients, projects, lines and time entries. This only takes effect in
  databases created from now on; older ones keep SQLite's default id reuse until there is a
  migration story.
- An invoice built from tracked time plus 200 fixed lines is refused at creation instead of
  becoming a draft that can never be saved or sent.
- The PDF no longer fails (500) on a line description with many line breaks (possible
  through the API); line descriptions print as one paragraph.
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

- README: Node 22.12+ is required (Vite 8's floor), 22.18+ for `make test`.
- CI signs in to the Docker container, downloads an invoice PDF, checks that `TZ` takes
  effect and runs the backup commands from the README.
- README: how to change the password, quoting in `.env`, `PYTHON=` for older systems, Docker
  upgrades and backups, the shared login lockout behind Docker, the PDF font's limits.
- The empty dashboard points to Settings for the invoice header details.
- Removed unused re-exports from `db.py`.

### Checked, no change needed

- Second fresh-clone pass (round 1, first-run lens): `make seed`, `make run`, `make dev`,
  `make test`, `make lint` and `make e2e` all work as the README says on macOS with
  Python 3.12 and Node 22.

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
  two Playwright specs (the main flow, then edits and undo paths; a phone-width spec came later), and a CI workflow that also builds and boots the Docker image.

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
