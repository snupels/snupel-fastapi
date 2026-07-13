# AGENTS.md

## Project

- Python 3.12 FastAPI backend managed with `uv`.
- Preserve the existing `/api/*` contract and MySQL schema compatibility.

## Working rules

- Make the smallest change that solves the requested problem; reuse existing code before adding abstractions or dependencies.
- Follow the existing `dto.py` → `repository.py` → `service.py` → `router.py` module structure.
- Reuse the shared CRUD helpers in `app/repository.py`, `app/service.py`, and `app/router.py` when they fit.
- Keep API paths, status codes, response shapes, and `{ "error", "message" }` error bodies backward compatible unless the task explicitly changes the contract.
- Use async SQLAlchemy sessions for database access. Put schema changes in a new Alembic migration; do not rewrite applied migrations.
- Never commit `.env`, credentials, tokens, or production data. Add new configuration keys to `.env.example` without secrets.
- Add or update test code with every code change so the changed behavior is covered.

## Verification

Run the relevant tests while verifying every change. Before handing off code changes, run the full suite:

```bash
uv run ruff check .
uv run pytest
```

If dependencies change, update `pyproject.toml` and `uv.lock` together.
