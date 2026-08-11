import os


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    if os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError("DATABASE_URL is required in production.")
    return "mysql+aiomysql://snupel:snupel@127.0.0.1:3306/snupel"


def admins() -> set[str]:
    return {
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }


def production_secret(name: str, value: str | None) -> str | None:
    if os.getenv("ENVIRONMENT") == "production" and (
        not value or len(value.encode()) < 32
    ):
        raise RuntimeError(f"{name} must be at least 32 bytes in production.")
    return value
