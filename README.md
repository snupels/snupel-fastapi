# snupel-fastapi

Snupel의 FastAPI 백엔드입니다. 기존 `/api/*` 계약과 MySQL 스키마를 유지합니다.

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

기존 Drizzle 스키마가 이미 적용된 DB는 테이블을 다시 만들지 않고 다음 명령으로 Alembic 기준점만 기록합니다.

```bash
uv run alembic stamp head
```

검증:

```bash
uv run pytest
uv run ruff check .
```

- Swagger UI: `/docs`
- OpenAPI JSON: `/api/docs`
- Health check: `/api/health`

