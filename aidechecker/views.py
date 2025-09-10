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
from io import BytesIO
import json
from .utils import save_report_as_pdf, format_aide_data, convert_aide_timestamps


local_timezone = pytz.timezone("Asia/Karachi")

CONFIG_PATH = "/home/Abdullah/backend_env_311_linux/aide.conf.copy"

REAL_CONFIG_PATH = "/etc/aide.conf"


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
            capture = False
            filtered_lines = []
            for line in lines:
                if line.startswith("Start timestamp:"):
                    capture = True
                if capture and not line.startswith("WARNING:"):
                    filtered_lines.append(convert_aide_timestamps(line))

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
                output="\n".join(filtered_lines),  
            )

            return JsonResponse({
                "success": True,
                "status": scan_record.status,
                "scan_id": scan_record.id,
                "run_time": scan_record.run_time.isoformat(),
                "files_changed": files_changed,
                "files_added": files_added,
                "files_removed": files_removed,
                "files_affected": files_affected,
                "output_preview": "\n".join(filtered_lines[:20]),  
                "stderr": result.stderr
            })

        except Exception as e:
            return JsonResponse({'success': False, 'output': str(e)}, status=500)

    return JsonResponse({'success': False, 'output': 'Only GET allowed'}, status=405)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def view_report(request, scan_id):
    try:
        scan = AideScanResult.objects.get(pk=scan_id)
        
        if not scan.output:
            raise Http404("No report data available")

        lines = scan.output.splitlines()
        parsed_data = format_aide_data(lines)

        return JsonResponse({
            "success": True,
            "data": parsed_data
        })

    except AideScanResult.DoesNotExist:
        raise Http404("Scan record not found")



@api_view(["GET"])
@permission_classes([IsAdminUser])
def download_report(request, scan_id):
    try:
        scan = AideScanResult.objects.get(pk=scan_id)

        if not scan.output:
            raise Http404("No report data available")

        buffer = BytesIO()
        save_report_as_pdf(buffer, scan.output.splitlines())
        buffer.seek(0)

        filename = f"aide_report_{datetime.now(local_timezone).strftime('%d-%m-%Y_%H%M%S')}.pdf"
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type="application/pdf"
        )

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



@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def get_config(request):
    if request.method == "GET":
        try:
            if not os.path.exists(CONFIG_PATH):
                return JsonResponse(
                    {"success": False, "msg": f"Config file not found at {CONFIG_PATH}"},
                    status=404,
                )
            with open(CONFIG_PATH, "r") as f:
                content = f.read()
            return JsonResponse({"success": True, "data": content})
        except Exception as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=500)

    elif request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8"))
            new_config = body.get("config")
            if not new_config:
                return JsonResponse({"success": False, "msg": "No config data provided"}, status=400)

            with open(CONFIG_PATH, "w") as f:
                f.write(new_config)

            try:
                subprocess.run(
                    ["sudo", "cp", CONFIG_PATH, REAL_CONFIG_PATH],
                    check=True
                )
            except subprocess.CalledProcessError as e:
                return JsonResponse({
                    "success": False,
                    "msg": f"Config updated locally but failed to apply to system: {e.stderr if e.stderr else str(e)}"
                }, status=500)

            return JsonResponse({"success": True, "msg": "Config updated successfully!"})

        except Exception as e:
            return JsonResponse({"success": False, "msg": f"Error saving config: {str(e)}"}, status=500)

    return JsonResponse({"success": False, "msg": "Only GET/POST allowed"}, status=405)

    return JsonResponse(
        {"success": False, "error": "Only GET/POST allowed"}, status=405
    )