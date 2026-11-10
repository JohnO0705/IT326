"""Deliver reminders using the SMTP account configured on the backend."""

from email.message import EmailMessage
from email.utils import format_datetime
import smtplib
import ssl

from ITask import utc_now
from backend.config import Settings


class EmailSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, to: str, subject: str, body: str) -> None:
        self.settings.require_email_settings()
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = to
        message["Subject"] = " ".join(subject.splitlines())[:240]
        message["Date"] = format_datetime(utc_now())
        message.set_content(body)
        factory = smtplib.SMTP_SSL if self.settings.smtp_ssl else smtplib.SMTP
        kwargs = {"timeout": 10}
        if self.settings.smtp_ssl:
            kwargs["context"] = ssl.create_default_context()
        with factory(self.settings.smtp_host, self.settings.smtp_port, **kwargs) as smtp:
            if self.settings.smtp_starttls and not self.settings.smtp_ssl:
                smtp.starttls(context=ssl.create_default_context())
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)
