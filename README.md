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
- Admin UI: `/admin` (`ADMIN_EMAILS` 계정의 비밀번호 + 이메일 인증 코드)
- OpenAPI JSON: `/api/docs`
- Health check: `/api/health`

관리자 인증 메일은 `MAIL_FROM`, `MAIL_USERNAME`, `MAIL_PASSWORD`를 사용하며,
`MAIL_HOST`(기본 `smtp.daum.net`)와 `MAIL_PORT`(기본 `465`)로 SMTP 서버를 변경할 수 있습니다.

## 관광 데이터와 미션 인증

공공데이터포털의 디코딩 인증키를 `DATA_GO_KR_SERVICE_KEY`에 설정한 뒤 강원 관광정보를
동기화합니다.

```bash
uv run python -m app.jobs.sync_tourism
```

운영 서버의 매일 실행 예시는 `deploy/snupel-tourism-sync.service`와
`deploy/snupel-tourism-sync.timer`에 있습니다. 인증사진은 비공개 S3 호환 저장소 설정을,
맞춤코스는 `OPENROUTER_API_KEY`와 `OPENROUTER_MODEL`을 사용합니다.

## 프로젝트 구조

```text
app/
├── config/        # 설정과 비동기 DB 세션
├── deps/          # 인증·인가 의존성
├── models/        # SQLAlchemy 모델
├── repositories/  # 데이터베이스 접근
├── routes/        # FastAPI 라우터
├── schemas/       # Pydantic 요청·응답 스키마
├── services/      # 비즈니스 로직과 외부 연동
├── exceptions.py  # 공통 API 예외
└── main.py        # 애플리케이션 진입점
```
