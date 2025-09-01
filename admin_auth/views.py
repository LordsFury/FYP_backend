from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from django.http import JsonResponse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

@api_view(['POST'])
def admin_login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)
    if user and user.is_staff:
        refresh = RefreshToken.for_user(user)
        return JsonResponse({
            'success': True,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'username': user.username,
            'msg': 'Admin LoggedIn successfully'
        }, status=status.HTTP_200_OK)
    return JsonResponse({'success': False, 'msg': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
