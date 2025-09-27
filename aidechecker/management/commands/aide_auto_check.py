from django.core.management.base import BaseCommand
import subprocess, os, smtplib
from email.message import EmailMessage
from datetime import datetime
from django.conf import settings
from aidechecker.models import Alert
from aidechecker.utils import save_report_as_pdf, convert_aide_timestamps  

ADMIN_EMAIL = "iabdullahkhan100@gmail.com"
SENDER_EMAIL = settings.EMAIL_HOST_USER
SENDER_PASS = settings.EMAIL_HOST_PASSWORD 
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

class Command(BaseCommand):
    help = "Run automatic AIDE check, generate PDF, and send email"

    def handle(self, *args, **kwargs):
        result = subprocess.run(["sudo", "aide", "--check"], capture_output=True, text=True)
        output = result.stdout

        if not any(word in output for word in ["found differences", "added entries", "removed entries"]):
            self.stdout.write("No changes detected.")
            return

        reports_dir = os.path.join(settings.BASE_DIR, "aide_reports")
        os.makedirs(reports_dir, exist_ok=True)

        pdf_path = os.path.join(
            reports_dir,
            f"aide_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        save_report_as_pdf(pdf_path, [convert_aide_timestamps(l) for l in output.splitlines()])

        msg = EmailMessage()
        msg["Subject"] = f"[AIDE Alert] Security Changes Detected on {os.uname().nodename}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = ADMIN_EMAIL

        msg.set_content(
            f"""
        Dear Administrator,

        The AIDE monitoring system has detected file system changes on the host: {os.uname().nodename}.

        A detailed report has been generated and is attached to this email in PDF format.

        Please review the report at your earliest convenience to ensure these changes are authorized.

        Best regards,  
        AIDE Monitoring Service
        """
        )

        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
            msg.add_attachment(
                pdf_data,
                maintype="application",
                subtype="pdf",
                filename=os.path.basename(pdf_path)
            )

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASS)
            server.send_message(msg)

        alert = Alert.objects.create(
        host=os.uname().nodename,
        summary="AIDE detected file system changes. See attached PDF.",
        pdf_report=f"aide_reports/{os.path.basename(pdf_path)}"
        )

        self.stdout.write(f"Email sent to {ADMIN_EMAIL}")
