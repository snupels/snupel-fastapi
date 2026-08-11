# Snupel API

강원도 스포츠 관광 패스포트 **Snupel**의 FastAPI 백엔드입니다. 사용자 인증, 관광·활동·코스 조회, 패스포트 및 스탬프 수집, 인증 사진 제출, 날씨 조회와 맞춤 코스 추천을 제공합니다.

## 기술 구성

- Python 3.12, FastAPI, Pydantic
- SQLAlchemy 비동기 ORM, MySQL, Alembic
- `uv` 패키지 관리
- SQLAdmin 관리자 화면

## 빠른 시작

사전 요구 사항: Python 3.12, [uv](https://docs.astral.sh/uv/), MySQL

```bash
git clone <repository-url>
cd snupel-fastapi
Copy-Item .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

서버를 실행한 뒤 다음 주소에서 확인할 수 있습니다.

| 주소 | 용도 |
| --- | --- |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/api/docs` | OpenAPI JSON |
| `http://localhost:8000/api/health` | 헬스 체크 |
| `http://localhost:8000/admin` | 관리자 화면 |

## 환경 변수

`.env.example`을 복사해 `.env`를 만들고 필요한 값을 설정합니다. `.env`는 저장소에 커밋하지 않습니다.

| 변수 | 설명 |
| --- | --- |
| `DATABASE_URL` | 비동기 MySQL 연결 문자열 |
| `JWT_SECRET` | JWT 서명 비밀값 |
| `ADMIN_EMAILS` | 관리자 이메일 목록(쉼표 구분) |
| `AUTH_ALLOWED_REDIRECT_URIS` | OAuth 로그인 후 허용할 리디렉션 URI |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth 설정 |
| `KAKAO_CLIENT_ID`, `KAKAO_CLIENT_SECRET` | Kakao OAuth 설정 |
| `MAIL_*` | 관리자 로그인 인증 코드를 발송할 SMTP 설정 |
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 관광 정보 API의 디코딩 인증키 |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | 맞춤 코스 추천 모델 설정 |
| `S3_*`, `STAMP_IMAGE_BASE_URL` | 스탬프 인증 사진을 위한 S3 호환 저장소 설정 |

`MAIL_HOST`와 `MAIL_PORT`의 기본값은 각각 `smtp.daum.net`, `465`입니다. 관리자 화면은 `ADMIN_EMAILS`에 등록된 계정의 비밀번호와 이메일 인증 코드로 로그인합니다.

## 데이터베이스

새 데이터베이스에는 아래 명령으로 모든 마이그레이션을 적용합니다.

```bash
uv run alembic upgrade head
```

기존 Drizzle 스키마가 이미 적용된 데이터베이스는 테이블을 다시 생성하지 않고 Alembic 기준점만 기록합니다.

```bash
uv run alembic stamp head
```

## 주요 API

모든 서비스 API는 `/api` 아래에 있습니다. 세부 요청·응답 형식은 Swagger UI에서 확인하세요.

| 경로 | 기능 |
| --- | --- |
| `/api/auth` | 이메일·OAuth 인증 및 토큰 관리 |
| `/api/activities` | 스포츠·관광 활동 조회 |
| `/api/courses` | 관광 코스 조회 |
| `/api/course-recommendations` | 맞춤 코스 추천 |
| `/api/passports` | 사용자 패스포트 |
| `/api/badges`, `/api/collected-badges` | 배지와 수집 배지 |
| `/api/collected-stamps`, `/api/stamp-catalog` | 수집 스탬프와 스탬프 카탈로그 |
| `/api/stamp-submissions` | 스탬프 인증 사진 제출·검토 |
| `/api/weather` | 날씨 조회 |

## 관광 데이터 동기화

공공데이터포털 키를 `DATA_GO_KR_SERVICE_KEY`에 설정한 후 실행합니다.

```bash
uv run python -m app.jobs.sync_tourism
```

운영 환경에서는 `deploy/snupel-tourism-sync.service`와 `deploy/snupel-tourism-sync.timer`를 사용해 매일 한국 시간 04:00에 동기화합니다.

## 개발 및 검증

```bash
uv run ruff check .
uv run pytest
```

GitHub Actions는 PR과 `main` 브랜치 배포 전에 같은 검증을 실행합니다.

## 프로젝트 구조

```text
app/
├── config/        # 환경 설정과 비동기 DB 세션
├── deps/          # 인증·인가 의존성
├── jobs/          # 정기 실행 작업
├── models/        # SQLAlchemy 모델
├── repositories/  # 데이터베이스 접근 계층
├── routes/        # FastAPI 라우터
├── schemas/       # Pydantic 요청·응답 스키마
├── services/      # 비즈니스 로직과 외부 서비스 연동
├── static/        # 스탬프 정적 자산
├── admin.py       # SQLAdmin 설정
└── main.py        # 애플리케이션 진입점
alembic/           # DB 마이그레이션
deploy/            # systemd 서비스·타이머 예시
tests/             # 테스트
```
