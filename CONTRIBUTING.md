# Contributing

Thanks for looking. solodesk is a small project with a deliberately small scope (see the
Roadmap and "Compared with the alternatives" in the README), so open an issue before starting
anything large.

## Set up

You need Python 3.12+, Node 22.18+ and `make`.

```sh
make dev     # API with reload on :4150, UI with hot reload on :4151
make seed    # demo data
```

## Before you open a pull request

```sh
make test    # pytest, frontend unit tests, typecheck
make lint    # ruff
make e2e     # Playwright (once: cd frontend && npx playwright install chromium)
```

CI runs the same, then builds the Docker image.

## Ground rules

- Money is integer minor units. No floats anywhere an amount is computed. If you change the
  arithmetic, change `backend/solodesk/money.py` and `frontend/src/lib/money.ts` together and
  keep their tests in step.
- New logic gets a test; a bug fix gets a test that fails without the fix.
- Validate input at the API boundary and answer 4xx, never 500.
- No new dependency for something a few lines of standard library can do.
- Add a line under "Unreleased" in `CHANGELOG.md` for anything a user would notice.
- Do not put real client data, passwords or `.env` files in issues, screenshots or commits.

## Security

Please do not put exploit details in a public issue. Open an issue that says only that you
have a security report, and ask for a private way to send it.
