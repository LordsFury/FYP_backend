from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import AideScanResult
from django.conf import settings
from datetime import datetime
import pytz
import subprocess
import re
import os
from django.http import FileResponse, Http404
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import api_view, permission_classes
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import json

REPORTS_DIR = os.path.join(settings.BASE_DIR, "reports")

local_timezone = pytz.timezone("Asia/Karachi")

def convert_aide_timestamps(line):
    match = re.search(r'(Start|End)\s+timestamp:\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    if match:
        label = match.group(1)
        utc_str = match.group(2)
        try:
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
            utc_dt = pytz.utc.localize(utc_dt)
            local_dt = utc_dt.astimezone(local_timezone)
            return f"{label} timestamp: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            return line
    return line

def save_report_as_pdf(filepath, lines):
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    y = height - 50

    for line in lines:
        c.drawString(50, y, line)
        y -= 15
        if y < 50:  
            c.showPage()
            y = height - 50

    c.save()

@csrf_exempt
@api_view(["GET"])
@permission_classes([IsAdminUser])
def run_check(request):
    if request.method == 'GET':
        try:
            result = subprocess.run(
                ["sudo", "aide", "--check"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            lines = result.stdout.splitlines()
            filtered_lines = [
                convert_aide_timestamps(line)
                for line in lines
                if not line.startswith("WARNING:")
            ]

            os.makedirs(REPORTS_DIR, exist_ok=True)
            filename = f"aide_report_{datetime.now(local_timezone).strftime('%d-%m-%Y_%H%M%S')}.pdf"
            filepath = os.path.join(REPORTS_DIR, filename)

            report_file = save_report_as_pdf(filepath, filtered_lines)

            files_changed = 0
            files_added = 0
            files_removed = 0

            for line in lines:
                if "Changed entries:" in line:
                    match = re.search(r"Changed entries:\s*(\d+)", line)
                    if match:
                        files_changed = int(match.group(1))
                elif "Added entries:" in line:
                    match = re.search(r"Added entries:\s*(\d+)", line)
                    if match:
                        files_added = int(match.group(1))
                elif "Removed entries:" in line:
                    match = re.search(r"Removed entries:\s*(\d+)", line)
                    if match:
                        files_removed = int(match.group(1))
                else:
                    match = re.search(r"Found\s+(\d+)\s+entries\s+that\s+have\s+changed", line)
                    if match:
                        files_changed = int(match.group(1))
            files_affected = files_changed + files_added + files_removed

            scan_record = AideScanResult.objects.create(
                status="success" if result.returncode == 0 else "changes_found",
                run_time=datetime.now(local_timezone),
                files_changed=files_changed,
                files_added=files_added,
                files_removed=files_removed,
                files_affected=files_affected,
                output="\n".join(filtered_lines[:20]),
                report_file=filename
            )

            return JsonResponse({
                "success": True,
                "status": "success" if result.returncode == 0 else "changes_found",
                "scan_id": scan_record.id,
                "run_time": datetime.now(local_timezone).isoformat(),
                "files_changed": files_changed,
                "files_added": files_added,
                "files_removed": files_removed,
                "files_affected": files_affected,
                "output": "\n".join(filtered_lines[:20]),
                "report_file": filename,
                "stderr": result.stderr
            })

        except Exception as e:
            return JsonResponse({'success': 'error', 'output': str(e)}, status=500)

    return JsonResponse({'success': 'error', 'output': 'Only GET allowed'}, status=405)

@api_view(["GET"])
@permission_classes([IsAdminUser])
def download_report(request, scan_id):
    try:
        scan = AideScanResult.objects.get(pk=scan_id)
        file_path = os.path.join(REPORTS_DIR, scan.report_file)

        if not os.path.exists(file_path):
            raise Http404("Report not found")

        response = FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            content_type="application/pdf"
        )
        response["Content-Disposition"] = f'attachment; filename="{scan.report_file}"'
        return response
    except AideScanResult.DoesNotExist:
        raise Http404("Scan record not found")



@csrf_exempt
@api_view(["POST"])
@permission_classes([IsAdminUser])
def accept_changes(request):
    if request.method == 'POST':
        try:
            subprocess.run(["sudo", "aide", "--update"], check=False)
            subprocess.run([
                "sudo", "mv", "/var/lib/aide/aide.db.new", "/var/lib/aide/aide.db"
            ], check=True)

            return JsonResponse({
                "success": True,
                "output": "Changes accepted. Baseline updated."
            })
        except subprocess.CalledProcessError as e:
            return JsonResponse({"success": "error", "output": str(e)}, status=500)

    return JsonResponse({"success": "error", "output": "Only POST allowed"}, status=405)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_last_scan(request):
    last_scan = AideScanResult.objects.order_by('-run_time').first()
    if not last_scan:
        return JsonResponse({"success": "empty", "output": "No scans found"})

    return JsonResponse({
        "success": True,
        "status": last_scan.status,
        "scan_id": last_scan.id,
        "run_time": last_scan.run_time,
        "files_changed": last_scan.files_changed,
        "files_added": last_scan.files_added,
        "files_removed": last_scan.files_removed,
        "total_changes": last_scan.files_affected,
        "report_file": last_scan.report_file
    })

@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_all_data(request):
    if request.method == "GET":
        try:
            all_data_qs = AideScanResult.objects.order_by('-run_time')
            if not all_data_qs.exists():
                return JsonResponse({"success": "empty", "output": "No scans found"})
            all_data = list(all_data_qs.values())
            return JsonResponse({
                "success": True,
                "allData": all_data
            }, safe=False)
        except Exception as e:
            return JsonResponse({'success': 'error', 'output': str(e)}, status=500)

    return JsonResponse({'success': 'error', 'output': 'Only GET allowed'}, status=405)

@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def delete_data(request, scan_id):
    if request.method=="DELETE":
        try:
            data_to_delete = AideScanResult.objects.get(pk=scan_id)
            data_to_delete.delete()
            return JsonResponse({
                "success": True,
                "output": "Entry Deleted successfully"
            }, safe=False)
        except Exception as e:
            return JsonResponse({'success': 'error', 'output': str(e)}, status=500)

    return JsonResponse({'success': 'error', 'output': 'Only DELETE allowed'}, status=405)



@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def delete_all_data(request):
    if request.method=="DELETE":
        try:
            data_to_delete = AideScanResult.objects.all()
            data_to_delete.delete()
            return JsonResponse({
                "success": True,
                "output": "History Cleared successfully"
            }, safe=False)
        except Exception as e:
            return JsonResponse({'success': 'error', 'output': str(e)}, status=500)

    return JsonResponse({'success': 'error', 'output': 'Only DELETE allowed'}, status=405)



@csrf_exempt
@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def get_config(request):
    if request.method == "GET":
        try:
            result = subprocess.run(
                ["sudo", "aide-config", "read"],
                capture_output=True,
                text=True,
                check=True
            )
            return JsonResponse(
                {"success": True, "data": result.stdout, "mimetype": "text/plain"}
            )
        except subprocess.CalledProcessError as e:
            return JsonResponse(
                {"success": False, "msg": e.stderr}, status=500
            )
    elif request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8"))
            new_config = body.get("config")
            if not new_config:
                return JsonResponse(
                    {"success": False, "msg": "No config data provided"}, status=400
                )
            process = subprocess.run(
                ["sudo", "tee", "/etc/aide.conf"],
                input=new_config,
                text=True,
                capture_output=True
            )
            if process.returncode != 0:
                return JsonResponse({"success": False, "error": process.stderr}, status=500)

            return JsonResponse({"success": True, "msg": "Config updated successfully!"})

        except Exception as e:
            return JsonResponse(
                {"success": False, "error": str(e)}, status=500
            )

    return JsonResponse(
        {"success": False, "error": "Only GET/POST allowed"}, status=405
    )
