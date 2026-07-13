import os


def database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://snupel:snupel@127.0.0.1:3306/snupel",
    )


def admins() -> set[str]:
    return {
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }

