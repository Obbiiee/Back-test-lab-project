"""TLS-only SMTP delivery; tests inject their own sink, never a demo default."""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage


class SmtpDelivery:
    def __init__(self, host, username, password, sender, port=465):
        if not all(type(v) is str and v for v in (host, username, password, sender)):
            raise ValueError("SMTP configuration required")
        self.host, self.username, self.password, self.sender, self.port = host, username, password, sender, port

    async def send(self, email, purpose, token):
        def operation():
            message = EmailMessage()
            message["From"], message["To"] = self.sender, email
            message["Subject"] = "Backtest Lab account " + purpose
            message.set_content("Use this token only in your Backtest Lab " + purpose +
                                " request. It expires; do not share it.\n\n" + token)
            with smtplib.SMTP_SSL(self.host, self.port, timeout=10, context=ssl.create_default_context()) as smtp:
                smtp.login(self.username, self.password)
                smtp.send_message(message)
        await asyncio.to_thread(operation)
