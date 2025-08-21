import os
import requests

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
MAILGUN_FROM = os.getenv("MAILGUN_FROM")

def send_email(subject, recipients, body):
    """
    Send email using Mailgun HTTP API
    """
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        raise RuntimeError("Mailgun config missing (check .env)")

    response = requests.post(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        auth=("api", MAILGUN_API_KEY),
        data={
            "from": MAILGUN_FROM,
            "to": recipients,
            "subject": subject,
            "text": body
        }
    )

    if response.status_code != 200:
        raise RuntimeError(f"Mailgun API error: {response.status_code} {response.text}")

    return response.json()
