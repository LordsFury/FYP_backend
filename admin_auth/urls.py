from django.urls import path
from .views import admin_login, forgot_password, verify_reset_code, reset_password, current_admin, update_profile

urlpatterns = [
    path('api/admin-login/', admin_login, name='admin-login'),
    path('api/current-admin/', current_admin, name='current-admin'),
    path('api/update-profile/', update_profile, name='update-profile'),
    path('api/forgot-password/', forgot_password, name='forgot-password'),
    path('api/verify-reset-code/', verify_reset_code, name='verify-reset-code'),
    path('api/reset-password/', reset_password, name='reset-password'),
]
