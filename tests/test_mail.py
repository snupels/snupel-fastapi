from unittest.mock import MagicMock

from app.services.mail import send_mail


def test_send_mail(monkeypatch):
    monkeypatch.setenv("MAIL_FROM", "no-reply@example.com")
    monkeypatch.setenv("MAIL_USERNAME", "daum-id")
    monkeypatch.setenv("MAIL_PASSWORD", "app-password")
    smtp = MagicMock()
    monkeypatch.setattr("app.services.mail.smtplib.SMTP_SSL", smtp)

    send_mail("user@example.com", "Welcome", "Hello")

    smtp.assert_called_once_with("smtp.daum.net", 465, timeout=10)
    connection = smtp.return_value.__enter__.return_value
    connection.login.assert_called_once_with("daum-id", "app-password")
    message = connection.send_message.call_args.args[0]
    assert (message["From"], message["To"], message["Subject"]) == (
        "no-reply@example.com",
        "user@example.com",
        "Welcome",
    )
    assert message.get_content() == "Hello\n"
