from django.urls import path
from .views import admin_login

urlpatterns = [
    path('api/admin-login/', admin_login, name='admin-login'),
]
