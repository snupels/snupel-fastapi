# AGENTS.md

## Project

- Python 3.12 FastAPI backend managed with `uv`.
- Preserve the existing `/api/*` contract and MySQL schema compatibility.

## Working rules

- Make the smallest change that solves the requested problem; reuse existing code before adding abstractions or dependencies.
- Follow the layered flow: `routes` → `deps` → `services` → `repositories` → `models`.
- Put request/response validation in `app/schemas/`; keep HTTP concerns in `app/routes/` and business logic in `app/services/`.
- Reuse the shared CRUD helpers in `app/repositories/base.py`, `app/services/base.py`, and `app/routes/base.py` when they fit.
- Re-export model classes from `app/models/__init__.py` so existing `app.models` imports and Alembic metadata discovery remain stable.
- Keep API paths, status codes, response shapes, and `{ "error", "message" }` error bodies backward compatible unless the task explicitly changes the contract.
- Use async SQLAlchemy sessions for database access. Put schema changes in a new Alembic migration; do not rewrite applied migrations.
- Never commit `.env`, credentials, tokens, or production data. Add new configuration keys to `.env.example` without secrets.
- Add or update test code with every code change so the changed behavior is covered.

## Adding a feature

1. Add or update the SQLAlchemy model in `app/models/` and re-export it from `app/models/__init__.py`.
2. Add Pydantic schemas in `app/schemas/`.
3. Add database access in `app/repositories/` and business logic in `app/services/`.
4. Add the API router in `app/routes/` and register it in `app/main.py`.

## Verification

Run the relevant tests while verifying every change. Before handing off code changes, run the full suite:

```bash
uv run ruff check .
uv run pytest
```

If dependencies change, update `pyproject.toml` and `uv.lock` together.
