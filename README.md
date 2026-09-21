# Snupel FastAPI

강원도 스포츠 관광 패스포트 **Snupel**의 FastAPI 백엔드입니다. 회원 인증, 스포츠·관광 콘텐츠 탐색, 코스 추천, 패스포트·스탬프 수집, 인증 사진 제출, 커뮤니티 피드, 관리자 검수 기능을 제공합니다.

## 기술 스택

- Python 3.12
- FastAPI, Pydantic
- SQLAlchemy async ORM, MySQL, Alembic
- SQLAdmin
- `uv` 패키지 관리
- S3 호환 스토리지 업로드 URL 발급

## 빠른 시작

필요한 도구는 Python 3.12, `uv`, MySQL입니다.

```bash
git clone <repository-url>
cd snupel-fastapi
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

기본 개발 DB URL은 `mysql+aiomysql://snupel:snupel@127.0.0.1:3306/snupel`입니다. 다른 계정이나 호스트를 쓰면 `.env`의 `DATABASE_URL`을 바꾸면 됩니다.

서버 실행 후 확인할 수 있는 주소입니다.

| 주소 | 용도 |
| --- | --- |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/api/docs` | OpenAPI JSON |
| `http://localhost:8000/api/health` | 헬스 체크 |
| `http://localhost:8000/admin` | SQLAdmin 관리자 화면 |

## 환경 변수

`.env.example`을 복사해 `.env`를 만들고 로컬 값으로 채웁니다. `.env`에는 비밀값이 들어가므로 커밋하지 않습니다.

| 변수 | 설명 |
| --- | --- |
| `DATABASE_URL` | 비동기 MySQL 연결 문자열. 개발 환경에서는 없으면 로컬 기본값을 사용합니다. |
| `ENVIRONMENT` | `development` 또는 `production`. production에서는 DB URL과 충분히 긴 비밀값 검사가 강화됩니다. |
| `JWT_SECRET` | API 액세스 토큰 서명 비밀값. production에서는 32바이트 이상이어야 합니다. |
| `ADMIN_SESSION_SECRET` | 관리자 세션 쿠키 서명 비밀값. 없으면 `JWT_SECRET`을 사용합니다. |
| `ADMIN_EMAILS` | SQLAdmin 로그인 허용 이메일 목록. 쉼표로 여러 개를 지정합니다. |
| `AUTH_ACCESS_TOKEN_EXPIRES_IN` | 액세스 토큰 만료 시간(초). 기본값은 604800초입니다. |
| `AUTH_ALLOWED_REDIRECT_URIS` | OAuth 로그인 후 허용할 리디렉션 URI 목록. production에서는 반드시 등록된 URI만 허용됩니다. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth 설정. |
| `KAKAO_CLIENT_ID`, `KAKAO_CLIENT_SECRET` | Kakao OAuth 설정. `KAKAO_CLIENT_ID`는 관광 데이터 주소·좌표 보완에도 사용됩니다. |
| `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | 관리자 로그인 OTP, 계정 찾기, 비밀번호 재설정 메일 발송 설정. |
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 관광·날씨 API 인증키. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODEL` | AI 코스 추천에 사용할 OpenRouter 설정. 키가 없으면 서비스의 fallback 추천 로직을 사용합니다. |
| `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | 인증 사진과 프로필 이미지 업로드 URL 발급에 사용할 S3 호환 스토리지 설정. |
| `STAMP_IMAGE_BASE_URL` | 스탬프 이미지가 CloudFront 같은 별도 도메인으로 제공될 때 쓰는 공개 base URL. |

`MAIL_HOST`와 `MAIL_PORT`의 기본값은 각각 `smtp.daum.net`, `465`입니다.

## 데이터베이스

새 데이터베이스에는 모든 Alembic 마이그레이션을 적용합니다.

```bash
uv run alembic upgrade head
```

이미 기존 스키마가 적용된 데이터베이스를 Alembic 관리 대상으로만 연결해야 할 때는 현재 head를 기준점으로 기록합니다.

```bash
uv run alembic stamp head
```

스키마를 바꾸는 기능을 추가할 때는 기존 migration을 수정하지 말고 `alembic/versions/`에 새 migration을 추가합니다.

## API 영역

모든 서비스 API는 `/api` 아래에 있습니다. 요청·응답 스키마와 세부 파라미터는 `/docs`에서 확인하세요.

| 경로 | 기능 |
| --- | --- |
| `/api/auth` | 회원가입, 로그인, 내 인증 정보, 프로필 수정, OAuth, 비밀번호 재설정 |
| `/api/activities`, `/api/activities/map` | 스포츠·관광 활동 CRUD와 지도 범위 조회 |
| `/api/sports`, `/api/events` | 스포츠 체험과 행사 탐색 |
| `/api/courses` | 관광 코스 CRUD와 일정 조회 |
| `/api/course-recommendations` | 사용자 조건 기반 코스 추천 |
| `/api/passports` | 사용자 패스포트와 미션 진행 현황 |
| `/api/badges`, `/api/collected-badges` | 배지 카탈로그와 사용자 수집 배지 |
| `/api/stamp-catalog`, `/api/collected-stamps` | 스탬프 카탈로그와 사용자 수집 스탬프 |
| `/api/stamp-submissions` | 인증 사진 업로드 URL 발급, 제출, 내 제출 목록, 피드 공개 설정 |
| `/api/community-feed` | 공개 인증 피드, 좋아요, 댓글, 내 피드, 팔로잉 피드 |
| `/api/community-profiles` | 커뮤니티 프로필 조회와 팔로우/언팔로우 |
| `/api/me` | 마이페이지 배지, 저장한 활동, 활동 기록, 리워드 신청 |
| `/api/weather` | 지역·좌표 기반 날씨 조회 |
| `/api/admin/*` | 관리자용 리워드 신청, 코스 미션 생성, 스탬프 제출 검수 |

인증이 필요한 API는 `Authorization: Bearer <token>` 헤더를 사용합니다. 공통 오류 응답은 기존 클라이언트 호환을 위해 `{ "error": "...", "message": "..." }` 형태를 유지합니다.

## 관광 데이터 동기화

공공데이터포털 키를 `DATA_GO_KR_SERVICE_KEY`에 설정한 뒤 실행합니다.

```bash
uv run python -m app.jobs.sync_tourism
```

동기화 작업은 TourAPI, 두루누비, 산림청·강원도 스포츠 관련 데이터 등을 읽어 `activities` 데이터를 보강합니다. Kakao REST API 키가 있으면 주소와 좌표 보정에도 사용합니다.

운영 서버 예시는 `deploy/`에 있습니다.

- `deploy/snupel-fastapi.service`: API 서버 systemd 서비스
- `deploy/snupel-tourism-sync.service`: 관광 데이터 동기화 1회 실행 서비스
- `deploy/snupel-tourism-sync.timer`: 매일 한국 시간 04:00 동기화 타이머

## 관리자 화면

관리자 화면은 `/admin`에서 SQLAdmin으로 제공됩니다. `ADMIN_EMAILS`에 등록된 사용자만 로그인할 수 있고, 로그인에는 계정 비밀번호와 이메일 OTP가 필요합니다. OTP 발송을 위해 `MAIL_*` 설정이 필요합니다.

관리자 API는 `require_admin` 의존성을 사용합니다. 관리자 계정도 일반 로그인 API에서 발급된 JWT를 사용하며, 이메일이 `ADMIN_EMAILS`에 포함되어야 합니다.

## 개발 규칙

코드는 계층 흐름을 유지합니다.

```text
routes -> deps -> services -> repositories -> models
```

- HTTP 요청·응답 처리는 `app/routes/`에 둡니다.
- 요청·응답 검증 모델은 `app/schemas/`에 둡니다.
- 비즈니스 로직은 `app/services/`, DB 접근은 `app/repositories/`에 둡니다.
- SQLAlchemy 모델은 `app/models/`에 두고 `app/models/__init__.py`에서 다시 export합니다.
- 새 테이블이나 컬럼이 필요하면 새 Alembic migration을 추가합니다.
- `/api/*` 경로, 상태 코드, 응답 shape, 오류 body는 기존 클라이언트와 호환되게 유지합니다.

## 검증

변경 전후로 관련 테스트를 먼저 돌리고, 전달 전에는 전체 검증을 실행합니다.

```bash
uv run ruff check .
uv run pytest
```

의존성을 바꾸면 `pyproject.toml`과 `uv.lock`을 함께 업데이트합니다.

## 프로젝트 구조

```text
app/
├── config/        # 환경 설정과 비동기 DB 세션
├── deps/          # 인증, 관리자 권한, rate limit 의존성
├── jobs/          # 관광 데이터 동기화 작업
├── models/        # SQLAlchemy 모델과 enum
├── repositories/  # DB 접근 계층
├── routes/        # FastAPI 라우터
├── schemas/       # Pydantic 요청·응답 스키마
├── services/      # 비즈니스 로직과 외부 API 연동
├── static/        # 스탬프 정적 이미지
├── admin.py       # SQLAdmin 설정
└── main.py        # FastAPI 앱 생성과 라우터 등록

alembic/           # DB 마이그레이션
deploy/            # systemd 배포 예시
tests/             # pytest 테스트
```
