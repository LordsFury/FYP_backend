from django.db import models
from django.utils import timezone

class AideScanResult(models.Model):
    status = models.CharField(default="", max_length=20)
    run_time = models.DateTimeField()
    files_changed = models.IntegerField(default=0)
    files_added = models.IntegerField(default=0)
    files_removed = models.IntegerField(default=0)
    files_affected = models.IntegerField(default=0)
    output = models.TextField()
    report_file = models.CharField(max_length=255)

    def __str__(self):
        return f"AIDE Scan - {self.run_time.strftime('%Y-%m-%d %H:%M:%S')}"



class Alert(models.Model):
    timestamp = models.DateTimeField(default=timezone.now)
    host = models.CharField(max_length=100)
    summary = models.TextField()
    pdf_report = models.FileField(upload_to="aide_reports/", null=True, blank=True)
    is_read = models.BooleanField(default=False)
    status = models.CharField(max_length=50, default="Changes Detected")  
    files_changed = models.IntegerField(default=0)
    files_added = models.IntegerField(default=0)
    files_removed = models.IntegerField(default=0)
    output = models.TextField(blank=True)  

    def __str__(self):
        return f"Alert on {self.host} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
