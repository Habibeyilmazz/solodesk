# solodesk

A self-hosted back office for freelancers and tiny studios: clients, projects, a timer, and
numbered PDF invoices in TRY, USD, EUR or GBP. It runs as one small app on your own machine,
with your books in a single SQLite file that never leaves it.

![The solodesk dashboard with a running timer, revenue per month, unpaid invoices, top clients and hours this week](docs/screenshots/dashboard.png)

## Quickstart

You need Python 3.12+, Node 22.12+ (22.18+ for `make test`) and `make`.

```sh
git clone https://github.com/Habibeyilmazz/solodesk.git
cd solodesk
make seed   # optional: fill the empty database with demo data
make run    # installs what is missing, builds the UI, serves http://localhost:4150
```

The first run copies `.env.example` to `.env`. Sign in with the password in that file
(`change-me-please`). Before you put real data in, change `SOLODESK_PASSWORD` in `.env` and
start solodesk again: that also signs out every session opened with the old password. Then
fill in your business details under Settings; they are the header of every invoice.

If `python3` on your machine is older than 3.12 (macOS ships 3.9), `make` stops and says so.
Name a newer one: `make run PYTHON=python3.12`.

With Docker instead:

```sh
cp .env.example .env          # then edit SOLODESK_PASSWORD
docker compose up -d          # http://localhost:4150
docker compose run --rm solodesk python -m solodesk.seed   # optional demo data
```

After pulling a newer version, rebuild with `docker compose up -d --build`.

## What it does

- **Clients and projects.** Each client has an invoice currency; each project has an hourly rate.
- **Time tracking.** A timer bar on every page (start, stop, one timer at a time) and manual
  entries typed as `1:30`, `1.5` or `90m`. Entries can be marked not billable.
- **Invoices.** Build a draft from a client's unbilled time (one line per project), from fixed
  line items, or both. Percentage discount and tax, totals updated as you type.
- **Sequential numbers.** An invoice gets its number (`INV-0001`, prefix configurable) when you
  mark it sent, so deleted drafts never leave a gap. Sent invoices are locked, and their PDF
  keeps printing your details and the client's as they were on the day it was sent.
- **Status flow.** Draft, sent, paid, with overdue shown automatically once the due date passes.
  A payment marked by mistake can be undone.
- **PDF export** with your business details, the client's, and Turkish characters and ₺ intact
  ([sample](docs/sample-invoice.pdf)). The bundled font has no Chinese, Japanese or Korean
  glyphs, so text in those scripts will not print.
- **Dashboard.** Revenue per month for the last 12 months, unpaid and overdue totals with the
  invoices to chase, hours this week, and top clients. Shown per currency; nothing is converted.
- **CSV export** of invoices and time entries.
- **Single-user sign-in** with a password from the environment.

| Time log | Invoice |
| --- | --- |
| ![Time entries grouped by day, with a form to add time by hand](docs/screenshots/time.png) | ![An overdue invoice with its lines, totals and an overdue stamp](docs/screenshots/invoice-overdue.png) |
| ![Clients with their projects, hourly rates and unbilled time](docs/screenshots/clients.png) | ![A draft invoice being edited](docs/screenshots/invoice-draft.png) |
| ![The invoice list with status filters](docs/screenshots/invoices.png) | <img src="docs/screenshots/phone-dashboard.png" width="250" alt="The dashboard on a phone-sized screen"> |

All screenshots are of the running app with the demo data from `make seed`.

## How it works

One FastAPI process serves a JSON API under `/api` and the built React app everywhere else.
Data lives in `data/solodesk.db` (SQLite). Back it up by copying that file while solodesk is
stopped, or with `sqlite3 data/solodesk.db ".backup copy.db"` while it runs. With Docker the
database is in the `solodesk-data` volume:

```sh
docker compose stop
docker compose cp solodesk:/data/solodesk.db ./solodesk-backup.db
docker compose start
```

```
backend/solodesk/   FastAPI app: models, routers, money arithmetic, PDF, seed script
backend/tests/      pytest API and unit tests
frontend/src/       React + TypeScript UI
frontend/e2e/       Playwright tests: the main flow, then edits and undo paths
```

**Money is never a float.** Amounts are integers in minor units (kuruş, cents, pence),
quantities are integer hundredths and rates are basis points. Rounding happens once per line
and once each for discount and tax, half up. The browser's live preview uses the same integer
arithmetic as the server (`frontend/src/lib/money.ts` mirrors `backend/solodesk/money.py`), and
amounts typed into forms are parsed from their digits rather than through `parseFloat`.

**Tracked time becomes hours with two decimals.** 110 minutes is billed as 1.83 h, so quantity
times rate equals the amount printed on the invoice.

**Sign-in.** The password comes from `SOLODESK_PASSWORD` and is hashed with scrypt at startup;
set `SOLODESK_PASSWORD_HASH` instead to keep the plain password out of the environment
(`.venv/bin/python -m solodesk.auth` prints a hash). Signing in creates a server-side session
that lasts 14 days, sent in an `HttpOnly`, `SameSite=Strict` cookie. The database keeps only an
HMAC of the cookie, keyed from the password, so a copy of the database holds no usable cookies
and changing the password ends every session. Every write must also carry the session's CSRF
token in an `X-CSRF-Token` header. Five failed logins from one address lock that address out
for 15 minutes. With Docker, or behind a reverse proxy on another machine, every visitor
arrives from the same address, so the lockout then applies to all of them together; sessions
that are already open keep working.

**API docs.** The OpenAPI schema and Swagger UI are at `/api/docs` on a running instance.

## Configuration

| Variable | Meaning |
| --- | --- |
| `SOLODESK_PASSWORD` | The sign-in password, at least 8 characters. Required unless a hash is set. Single-quote it in `.env` if it has spaces or symbols. |
| `SOLODESK_PASSWORD_HASH` | A hash from `.venv/bin/python -m solodesk.auth`, used instead of the password. Single-quote it in `.env`. |
| `SOLODESK_DATA_DIR` | Folder for the SQLite database. Default `data`. |
| `SOLODESK_COOKIE_SECURE` | Set to `1` when serving over HTTPS so the cookie is marked `Secure`. |
| `TZ` | Time zone that decides when "today" starts for timers and due dates, for example `Europe/Istanbul`. Default: the machine's zone with `make run`, UTC with Docker. |

solodesk listens on `127.0.0.1` by default. To reach it from elsewhere, put a reverse proxy
with TLS in front and set `SOLODESK_COOKIE_SECURE=1`.

## Development

```sh
make dev    # API with reload on :4150, UI with hot reload on http://localhost:4151
make test   # pytest, frontend unit tests, typecheck
make lint   # ruff
make e2e    # Playwright tests against the built app (once: cd frontend && npx playwright install chromium)
```

CI runs all of these on every push, then builds the Docker image and checks that the
container starts, serves the app, produces an invoice PDF, honours `TZ` and can be backed up
as described above.

## Roadmap

Not built yet:

- Fixed-amount discounts and per-line tax rates
- Credit notes or voiding a sent invoice
- Adding more tracked time to an existing draft, and per-entry detail lines
- A warning before leaving a draft invoice with unsaved edits
- A phone layout for the wider tables (today they scroll sideways)
- Expenses and recurring invoices
- Emailing invoices from the app
- Schema migrations (0.1 creates tables on first start and has no upgrade path yet)
- A Turkish interface and locale-specific number formats
- Currency conversion for combined totals

## License

MIT, see [LICENSE](LICENSE). Invoice PDFs embed DejaVu Sans, which ships under its own
permissive licence in `backend/solodesk/fonts/`.
