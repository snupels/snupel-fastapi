import os
import smtplib
from email.message import EmailMessage


def send_mail(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL(
        os.getenv("MAIL_HOST", "smtp.daum.net"),
        int(os.getenv("MAIL_PORT", "465")),
        timeout=10,
    ) as smtp:
        smtp.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(message)
