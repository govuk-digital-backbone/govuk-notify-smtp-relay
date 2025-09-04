import os
import time
import requests
import ipaddress

from aiosmtpd.controller import Controller
from notifications_python_client.notifications import NotificationsAPIClient

from message_handling import parse_email

SMTP_HOSTNAME = os.getenv("SMTP_HOSTNAME", "127.0.0.1")
SMTP_PORT = int(os.getenv("SMTP_PORT", 2525))

NOTIFY_API_KEY = os.getenv("NOTIFY_API_KEY", None)
NOTIFY_TEMPLATE_ID = os.getenv("NOTIFY_TEMPLATE_ID", None)

NOTIFY_BASE_URL = os.getenv(
    "NOTIFY_BASE_URL",
    "https://api.notifications.service.gov.uk"
)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", None)

notifications_client = (
    NotificationsAPIClient(NOTIFY_API_KEY, base_url=NOTIFY_BASE_URL)
    if NOTIFY_API_KEY
    else None
)

def is_private_ip(ip):
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False

class NotifyHandler:
    async def handle_DATA(self, server, session, envelope):
        print("Received email data")

        # get sender/source IP address
        source_ip = session.peer[0] if session.peer else None
        if not is_private_ip(source_ip):
            print(f"Source IP {source_ip} is not private, skipping email processing")
            return "550 Source IP unacceptable"

        parsed = parse_email(envelope.content)
        recipients = parsed.get("recipients", [])
        subject = parsed.get("subject", None)
        body = parsed.get("body", None)

        if not recipients:
            return "550 No recipient found"

        if not subject or not body:
            return "550 Invalid email content"

        errors = 0
        try:
            for to in recipients:
                to = to.strip()
                if not to:
                    continue

                if SLACK_WEBHOOK_URL:
                    slack_payload = {
                        "to": to,
                        "subject": subject,
                        "body": body,

                    }
                    r = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
                    r.raise_for_status()
                    print(f"Relayed email to Slack for {to}")
                    
                if notifications_client and NOTIFY_TEMPLATE_ID:
                    response = notifications_client.send_email_notification(
                        email_address=to,
                        template_id=NOTIFY_TEMPLATE_ID,
                        personalisation={
                            "subject": subject,
                            "body": body,
                        }
                    )
                    print(f"Relayed email to {to} via GOV.UK Notify")

            return "250 Message accepted"
        except Exception as e:
            print(f"Notify relay failed: {e}")
            return "451 Temporary failure"


if __name__ == "__main__":
    controller = Controller(NotifyHandler(), hostname=SMTP_HOSTNAME, port=SMTP_PORT)
    print(f"Starting SMTP relay on port {SMTP_PORT}")
    controller.start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Stopping SMTP relay")
        controller.stop()
