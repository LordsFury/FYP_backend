from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import AideScanResult, Alert
from django.conf import settings
from datetime import datetime
import pytz
import subprocess
import re
import os
import shutil
from django.http import FileResponse, Http404
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import api_view, permission_classes
from io import BytesIO
import json
from .utils import save_report_as_pdf, format_aide_data, convert_aide_timestamps, extract_rules, extract_directories

local_timezone = pytz.timezone("Asia/Karachi")

CONFIG_PATH = "/home/Abdullah/backend_env_311/aide.conf.copy"

REAL_CONFIG_PATH = "/etc/aide.conf"

SYNC_SCRIPT = "/usr/local/bin/update_aide_conf.sh"

TIMER_FILE = "/etc/systemd/system/aide-auto-check.timer"


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
            return JsonResponse({
                "success": True,
                "message": "No detailed report available for this scan.",
                "data": {}
            })

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
    if request.method != 'POST':
        return JsonResponse({
            "success": "error",
            "output": "Only POST allowed"
        }, status=405)

    try:
        # Step 1: Run AIDE update (ignore exit code 7)
        subprocess.run(
            ["sudo", "/usr/bin/aide", "--update"],
            check=False
        )

        # Step 2: Replace main baseline DB
        subprocess.run(
            ["sudo", "/bin/mv", "/var/lib/aide/aide.db.new", "/var/lib/aide/aide.db"],
            check=True
        )

        # Step 3: Keep /etc/aide/aide.db in sync
        subprocess.run(
            ["sudo", "/bin/cp", "/var/lib/aide/aide.db", "/etc/aide/aide.db"],
            check=True
        )

        return JsonResponse({
            "success": True,
            "output": "Changes accepted. Baseline updated and persisted."
        })

    except subprocess.CalledProcessError as e:
        return JsonResponse({
            "success": "error",
            "output": f"Command failed: {e}"
        }, status=500)



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
            dirs = extract_directories(CONFIG_PATH)
            rules = extract_rules(CONFIG_PATH)
            return JsonResponse({"success": True, "directories": dirs, "rules": rules})
        except FileNotFoundError as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=500)

    elif request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            directories = data.get("directories", [])

            if not isinstance(directories, list):
                return JsonResponse({"success": False, "msg": "Invalid data format"}, status=400)

            valid_directories = []
            seen = set()

            for d in directories:
                path = d.get("path", "").strip()
                rule = d.get("rule", "").strip()

                if not path.startswith("/"):
                    return JsonResponse({"success": False, "msg": f"Invalid path (must start with /): {path}"}, status=400)

                if not re.match(r"^[/\w\.\-\*\$]+$", path):
                    return JsonResponse({"success": False, "msg": f"Invalid characters in path: {path}"}, status=400)

                # allow non-existent system dirs only if using * or $ 
                if "*" not in path and "$" not in path and not os.path.exists(path):
                    return JsonResponse({"success": False, "msg": f"Path does not exist: {path}"}, status=400)

                if (path, rule) in seen:
                    return JsonResponse({"success": False, "msg": f"Duplicate entry: {path} with rule {rule}"}, status=400)

                seen.add((path, rule))
                valid_directories.append({"path": path, "rule": rule})

            # Backup config
            if os.path.exists(CONFIG_PATH):
                shutil.copy(CONFIG_PATH, f"{CONFIG_PATH}.bak")

            new_lines = []
            with open(CONFIG_PATH, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        # keep comments and empty lines
                        new_lines.append(line)
                        continue
                    if re.match(r"^(/[\w\/\.\-\*\$]+)\s+.+$", stripped):
                        # skip old directory entries completely
                        continue
                    if re.match(r"^/[\w\/\.\-\*\$]+$", stripped):
                        # also skip lines that are just bare paths with no rule
                        continue
                    # keep everything else (like database, ruleset definitions, etc.)
                    new_lines.append(line)

            # now add updated directories (always path + rule)
            for d in valid_directories:
                new_lines.append(f"{d['path']} {d['rule']}\n")


            with open(CONFIG_PATH, "w") as f:
                f.writelines(new_lines)

            # Sync with real config
            try:
                subprocess.run(["sudo", SYNC_SCRIPT], check=True)
            except subprocess.CalledProcessError as e:
                return JsonResponse({"success": False, "msg": f"Failed to sync real config: {e}"}, status=500)

            return JsonResponse({"success": True, "msg": "Config updated successfully"})

        except Exception as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=500)



    return JsonResponse({"success": False, "msg": "Only GET/POST allowed"}, status=405)


@permission_classes([IsAdminUser])
def browse_directories(request):
    path = request.GET.get("path", "/")  
    try:
        if not os.path.isdir(path):
            return JsonResponse({"success": False, "msg": "Invalid path"}, status=400)

        dirs = []
        for entry in os.scandir(path):
            if entry.is_dir():
                dirs.append(entry.path)

        return JsonResponse({"success": True, "directories": dirs})
    except Exception as e:
        return JsonResponse({"success": False, "msg": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_alerts(request):
    alerts = Alert.objects.order_by("-timestamp")
    data = []

    for a in alerts:
        data.append({
            "id": a.id,
            "timestamp": a.timestamp,
            "host": a.host,
            "summary": a.summary,
            "pdf_url": a.pdf_report.url if a.pdf_report else None,
            "is_read": a.is_read,
            "status": a.status,
            "output": a.output,
            "files_changed": a.files_changed,
            "files_added": a.files_added,
            "files_removed": a.files_removed,
        })

    return JsonResponse(data, safe=False)


@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def delete_alert(request, alert_id):
    try:
        alert = Alert.objects.get(id=alert_id)
        alert.delete()
        return JsonResponse({"status": "success", "message": "Alert deleted successfully"})
    except Alert.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Alert not found"}, status=404)


@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def delete_all_alerts(request):
    count, _ = Alert.objects.all().delete()
    return JsonResponse({"status": "success", "message": f"Deleted {count} alerts"})



@api_view(["POST"])
@permission_classes([IsAdminUser])
def marked_as_read(request):
    updated_count = Alert.objects.filter(is_read=False).update(is_read=True)

    return JsonResponse({
        "status": "success",
        "message": f"{updated_count} alerts marked as read."
    })

@api_view(["GET"])
def system_overview(request):
    try:
        dirs = extract_directories()
        total_monitored = len(dirs)

        last_scan = AideScanResult.objects.order_by("-run_time").first()
        last_scan_time = last_scan.run_time if last_scan else None

        # Count active (unread) alerts
        active_alerts = Alert.objects.filter(is_read=False).count()

        return JsonResponse({
            "success": True,
            "monitored_files": total_monitored,
            "active_alerts": active_alerts,
            "last_scan": last_scan_time.strftime("%d-%m-%Y %H:%M:%S") if last_scan_time else None,
            "last_scan_status": last_scan.status if last_scan else None,
            "files_changed": last_scan.files_changed if last_scan else 0,
            "files_added": last_scan.files_added if last_scan else 0,
            "files_removed": last_scan.files_removed if last_scan else 0,
        })

    except Exception as e:
        return JsonResponse({"success": False, "msg": str(e)}, status=500)


@api_view(["GET"])
def recent_activity(request):
    try:
        activity = []

        recent_alerts = Alert.objects.order_by("-timestamp")[:5]
        for a in recent_alerts:
            activity.append({
                "type": "alert",
                "message": f"Alert on host {a.host}: {a.status}",
                "time": a.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "files_changed": a.files_changed,
                "files_added": a.files_added,
                "files_removed": a.files_removed,
                "level": "critical" if a.files_changed > 0 else "info"
            })

        recent_scans = AideScanResult.objects.order_by("-run_time")[:3]
        for s in recent_scans:
            activity.append({
                "type": "scan",
                "message": f"Scan completed: {s.files_changed} changed, {s.files_added} added, {s.files_removed} removed",
                "time": s.run_time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": s.status
            })

        activity.sort(key=lambda x: x["time"], reverse=True)

        return JsonResponse({"success": True, "activity": activity})

    except Exception as e:
        return JsonResponse({"success": False, "msg": str(e)}, status=500)



@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def aide_auto_check(request):
    if request.method == "GET":
        try:
            with open(TIMER_FILE, "r") as f:
                lines = f.readlines()

            schedule = ""
            for line in lines:
                if line.strip().startswith("OnCalendar="):
                    schedule = line.strip().split("=", 1)[1]
                    break

            return JsonResponse({"success": True, "schedule": schedule})
        except Exception as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=500)

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode('utf-8'))
            schedule = data.get("schedule")
            if not schedule:
                return JsonResponse({"success": False, "msg": "Missing 'schedule' field"}, status=400)

            valid_presets = ["daily", "weekly", "monthly"]
            if schedule.lower() in valid_presets:
                schedule_map = {
                    "daily": "daily",
                    "weekly": "weekly",
                    "monthly": "monthly",
                }
                schedule = schedule_map[schedule.lower()]
            else:
                # Validate custom systemd format like "*-*-* 14:30:00"
                pattern = re.compile(
                    r"^(\*|\d{4})-(\*|0[1-9]|1[0-2])-(\*|0[1-9]|[12]\d|3[01])\s([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$"
                )
                if not pattern.match(schedule):
                    return JsonResponse({
                        "success": False,
                        "msg": "Invalid schedule format. Example: '*-*-* 14:30:00' for daily 2:30 PM."
                    }, status=400)
            
            with open(TIMER_FILE, "r") as f:
                lines = f.readlines()

            new_lines = []
            found = False
            for line in lines:
                if line.strip().startswith("OnCalendar="):
                    new_lines.append(f"OnCalendar={schedule}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"OnCalendar={schedule}\n")

            content = "".join(new_lines)
            subprocess.run(["sudo", "tee", TIMER_FILE], input=content.encode(), check=True)

            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "restart", "aide-auto-check.timer"], check=True)

            return JsonResponse({"success": True, "msg": f"Timer updated to '{schedule}' successfully."})

        except subprocess.CalledProcessError as e:
            return JsonResponse({"success": False, "msg": f"System command failed: {e}"}, status=500)
        except Exception as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=500)

            