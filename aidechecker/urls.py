from django.urls import path
from .views import run_check, download_report, view_report, accept_changes, get_last_scan, get_all_data, delete_data, delete_all_data, get_config, browse_directories, get_alerts 

urlpatterns = [
    path('api/run-check/', run_check, name='run_check'),
    path('api/download-report/<str:scan_id>/', download_report, name='download_report'),
    path('api/view-report/<str:scan_id>/', view_report, name='view_report'),
    path('api/accept-changes/', accept_changes, name='accept_changes'),
    path('api/last-scan/', get_last_scan, name='last_scan'),
    path('api/all-data/', get_all_data, name='all_data'),
    path('api/delete-data/<str:scan_id>/', delete_data, name='delete_data'),
    path('api/delete-all-data/', delete_all_data, name='delete_all_data'),
    path('api/aide/config/', get_config, name='get_config'),
    path("api/browse/", browse_directories, name="browse_directories"),
    path("api/alerts/", get_alerts, name="get_alerts")
]
