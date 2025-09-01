from django.db import models
from datetime import date

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
