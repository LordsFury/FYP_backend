from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from django.http import JsonResponse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
import json, random, string
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.permissions import IsAuthenticated, IsAdminUser


User = get_user_model()

@api_view(['POST'])
def admin_login(request):
    email = request.data.get('email')
    password = request.data.get('password')
    user = authenticate(request, username=email, password=password)
    
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_admin(request):
    user = request.user
    return JsonResponse({
        "success": True,
        "username": user.username,
        "email": user.email,
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@permission_classes([IsAdminUser])
def update_profile(request):
    if request.method != "PATCH":
        return JsonResponse({"success": False, "msg": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        user = request.user  

        new_username = data.get("username")
        current_password = data.get("current_password")
        new_password = data.get("new_password")

        force_logout = False;
        if new_password:
            if not current_password:
                return JsonResponse({"success": False, "msg": "Current password is required"}, status=400)
            if not user.check_password(current_password):
                return JsonResponse({"success": False, "msg": "Current password is incorrect"}, status=400)

            user.set_password(new_password)
            force_logout = True

        if new_username:
            user.username = new_username

        user.save()

        msg = "Profile updated successfully"
        if force_logout:  
            msg += ". Please log in again with new credentials."
        return JsonResponse({
            "success": True,
            "msg": msg,
            "force_logout": force_logout
        }, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "msg": str(e)}, status=500)



@csrf_exempt  
def forgot_password(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            email = data.get("email")

            if not email:
                return JsonResponse({"success": False, "msg": "Email is required"}, status=400)

            try:
                user = User.objects.get(email=email.strip())
                
            except User.DoesNotExist:
                return JsonResponse({"success": False, "msg": "User with this email does not exist"}, status=404)

            reset_code = ''.join(random.choices(string.digits, k=6))

            cache.delete(f"reset_code_{user.pk}")
            cache.set(f"reset_code_{user.pk}", reset_code, timeout=300)
            subject = "Your Password Reset Code"
            message = f"""
            Hello {user.username},

            We received a request to reset your password for your account. 
            Please use the following verification code to proceed:

                {reset_code}

            This code is valid for the next 5 minutes. 
            If you did not request a password reset, please ignore this email.

            Thank you,
            The AIDE Team
            """

            try:
                send_mail(
                    subject,
                    message,
                    settings.EMAIL_HOST_USER,  
                    [user.email],
                    fail_silently=False,
                )
            except Exception as e:
                print("EMAIL ERROR:", str(e))  
                return JsonResponse({"success": False, "msg": f"Email error: {str(e)}"}, status=500)


            return JsonResponse({"success": True, "msg": "Password reset code sent to your email"}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"success": False, "msg": "Invalid request method"}, status=405)



@csrf_exempt
def verify_reset_code(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            email = data.get("email")
            code = data.get("code")

            if not email or not code:
                return JsonResponse({"success": False, "msg": "Email and code are required"}, status=400)

            try:
                user = User.objects.get(email=email.strip())
            except User.DoesNotExist:
                return JsonResponse({"success": False, "msg": "User not found"}, status=404)

            cached_code = cache.get(f"reset_code_{user.pk}")

            if cached_code and cached_code == code:
                return JsonResponse({"success": True, "msg": "Code verified"}, status=200)
            else:
                return JsonResponse({"success": False, "msg": "Invalid or expired code"}, status=400)

        except Exception as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=500)

    return JsonResponse({"success": False, "msg": "Invalid request method"}, status=405)


@csrf_exempt
def reset_password(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            email = data.get("email")
            code = data.get("code")
            password = data.get("password")

            if not email or not code or not password:
                return JsonResponse({"success": False, "msg": "Email, code, and password are required"}, status=400)

            try:
                user = User.objects.get(email=email.strip())
            except User.DoesNotExist:
                return JsonResponse({"success": False, "msg": "User not found"}, status=404)

            cached_code = cache.get(f"reset_code_{user.pk}")

            if cached_code and cached_code == code:
                user.set_password(password)
                user.save()

                cache.delete(f"reset_code_{user.pk}")

                return JsonResponse({"success": True, "msg": "Password reset successful"}, status=200)
            else:
                return JsonResponse({"success": False, "msg": "Invalid or expired code"}, status=400)

        except Exception as e:
            return JsonResponse({"success": False, "msg": str(e)}, status=500)

    return JsonResponse({"success": False, "msg": "Invalid request method"}, status=405)