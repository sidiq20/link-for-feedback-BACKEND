import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Feedback App")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")

configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = BREVO_API_KEY

def send_email(subject, recipients, body):
    """
    Send email using Brevo (Sendinblue)
    """
    try:
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        # Support both string and list recipients
        to_list = [{"email": recipients}] if isinstance(recipients, str) else [{"email": r} for r in recipients]

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            sender={"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
            to=to_list,
            subject=subject,
            text_content=body
        )

        response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Email sent to {recipients}: {response}")
        return True

    except ApiException as e:
        print(f"❌ Brevo API error: {e}")
        return False
