from django.core.management.base import BaseCommand
import subprocess, os, smtplib, re
from email.message import EmailMessage
from datetime import datetime
from django.conf import settings
from aidechecker.utils import save_report_as_pdf, convert_aide_timestamps
from aidechecker.models import Alert  

ADMIN_EMAIL = "iabdullahkhan100@gmail.com"
SENDER_EMAIL = settings.EMAIL_HOST_USER
SENDER_PASS = settings.EMAIL_HOST_PASSWORD
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

class Command(BaseCommand):
    help = "Run automatic AIDE check, generate PDF, send email, and save alert"

    def handle(self, *args, **kwargs):
        # 1. Run AIDE check
        result = subprocess.run(["sudo", "aide", "--check"], capture_output=True, text=True)
        output = result.stdout.strip()

        # 2. Check if any differences found
        if not any(word in output for word in ["found differences", "added entries", "removed entries"]):
            self.stdout.write("No changes detected.")
            return

        files_changed = self.extract_stat(output, r"(?im)^\s*Changed entries\s*:\s*(\d+)")
        files_added = self.extract_stat(output, r"(?im)^\s*Added entries\s*:\s*(\d+)")
        files_removed = self.extract_stat(output, r"(?im)^\s*Removed entries\s*:\s*(\d+)")

        # 4. Generate PDF
        reports_dir = os.path.join(settings.BASE_DIR, "aide_reports")
        os.makedirs(reports_dir, exist_ok=True)
        pdf_filename = f"aide_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(reports_dir, pdf_filename)
        save_report_as_pdf(pdf_path, [convert_aide_timestamps(l) for l in output.splitlines()])

        msg = EmailMessage()
        msg["Subject"] = f"[AIDE Alert] Security Changes Detected on {os.uname().nodename}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = ADMIN_EMAIL
        msg.set_content(f"""
Dear Administrator,

The AIDE monitoring system has detected file system changes on the host: {os.uname().nodename}.

A detailed report has been generated and is attached to this email in PDF format.

Summary:
- Files Changed: {files_changed}
- Files Added: {files_added}
- Files Removed: {files_removed}

Please review the report at your earliest convenience to ensure these changes are authorized.

Best regards,
AIDE Monitoring Service
        """)

        with open(pdf_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="pdf",
                filename=pdf_filename
            )

        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASS)
                server.send_message(msg)
            self.stdout.write(f"Email sent successfully to {ADMIN_EMAIL}")
        except Exception as e:
            self.stdout.write(f"Failed to send email: {e}")

        Alert.objects.create(
            host=os.uname().nodename,
            status="Changes Detected",
            summary=f"Files changed: {files_changed}, added: {files_added}, removed: {files_removed}",
            files_changed=files_changed,
            files_added=files_added,
            files_removed=files_removed,
            output=output,
            pdf_report=f"aide_reports/{pdf_filename}",
        )

        self.stdout.write("Alert stored in database successfully.")

    # Helper function to extract integers safely
    def extract_stat(self, text, pattern):
        match = re.search(pattern, text)
        return int(match.group(1)) if match else 0
