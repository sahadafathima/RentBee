
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from .permissions import IsActiveUser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken,
    BlacklistedToken,
)
from rest_framework_simplejwt.exceptions import TokenError
from .models import (
    PendingSignup,
    PasswordResetOTP,
    Profile,
    EmailChangeOTP,
)
from .serializers import LoginSerializer,ProfileSerializer
from .email_service import (
    send_rentbee_otp_email,
    OTP_PURPOSE_SIGNUP,
    OTP_PURPOSE_PASSWORD_RESET,
    OTP_PURPOSE_EMAIL_CHANGE,
)


User = get_user_model()


def get_text(data, key):
    value = data.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def send_otp_email(subject, message, email, otp=None, purpose=OTP_PURPOSE_SIGNUP, expiry_minutes=10):
    """
    Unified OTP email dispatcher. Delegates to the centralized email service.
    """
    if otp:
        return send_rentbee_otp_email(
            to_email=email,
            otp=otp,
            purpose=purpose,
            expiry_minutes=expiry_minutes,
        )
    send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )


def otp_error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


# -------------------- SIGNUP --------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def send_signup_otp(request):
    full_name = get_text(request.data, "full_name")
    email = get_text(request.data, "email").lower()
    phone_number = get_text(request.data, "phone_number")
    password = request.data.get("password", "")

    if not isinstance(password, str):
        password = ""

    if not all([full_name, email, phone_number, password]):
        return otp_error("All fields are required.")

    if User.objects.filter(email__iexact=email).exists():
        return otp_error("An account with this email already exists.")

    if User.objects.filter(phone_number=phone_number).exists():
        return otp_error("This phone number is already registered.")

    other_pending = PendingSignup.objects.filter(
        phone_number=phone_number
    ).exclude(email__iexact=email).exists()

    if other_pending:
        return otp_error(
            "This phone number is used in another pending signup."
        )

    try:
        validate_password(password)
    except ValidationError as error:
        return Response(
            {"error": list(error.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"

    PendingSignup.objects.update_or_create(
        email=email,
        defaults={
            "full_name": full_name,
            "phone_number": phone_number,
            "password_hash": make_password(password),
            "otp_hash": make_password(otp),
            "expires_at": timezone.now() + timedelta(minutes=10),
            "attempts": 0,
        },
    )

    try:
        send_rentbee_otp_email(
            to_email=email,
            otp=otp,
            purpose=OTP_PURPOSE_SIGNUP,
            expiry_minutes=10,
        )
    except Exception:
        PendingSignup.objects.filter(email__iexact=email).delete()
        return Response(
            {
                "error": (
                    "Could not send the verification email. "
                    "Please try again."
                )
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {"message": "OTP sent. Please check your email."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_signup_otp(request):
    email = get_text(request.data, "email").lower()
    otp = get_text(request.data, "otp")

    if not email or not otp:
        return otp_error("Email and OTP are required.")

    pending = PendingSignup.objects.filter(
        email__iexact=email
    ).first()

    if pending is None:
        return otp_error(
            "Signup request not found. Please request a new OTP.",
            status.HTTP_404_NOT_FOUND,
        )

    if timezone.now() >= pending.expires_at:
        pending.delete()
        return otp_error("OTP expired. Please request a new OTP.")

    if pending.attempts >= 5:
        pending.delete()
        return otp_error(
            "Too many attempts. Please request a new OTP.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    pending.attempts += 1
    pending.save(update_fields=["attempts"])

    if not check_password(otp, pending.otp_hash):
        if pending.attempts >= 5:
            pending.delete()
            return otp_error(
                "Too many attempts. Please request a new OTP.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return otp_error("Invalid OTP.")

    if User.objects.filter(email__iexact=email).exists():
        pending.delete()
        return otp_error("An account with this email already exists.")

    if User.objects.filter(
        phone_number=pending.phone_number
    ).exists():
        pending.delete()
        return otp_error("This phone number is already registered.")

    user = User(
        email=pending.email,
        full_name=pending.full_name,
        phone_number=pending.phone_number,
        is_email_verified=True,
    )
    user.password = pending.password_hash
    user.save()

    pending.delete()

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "message": "Email verified and signup successful.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "user_id": user.pk,
                "full_name": user.full_name,
                "email": user.email,
                "phone_number": user.phone_number,
            },
        },
        status=status.HTTP_201_CREATED,
    )


# -------------------- USER LOGIN --------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def user_login(request):
    serializer = LoginSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = serializer.validated_data["email"].lower()
    password = serializer.validated_data["password"]

    user = authenticate(
        request,
        username=email,
        password=password,
    )

    if user is None:
        return otp_error(
            "Invalid email or password.",
            status.HTTP_401_UNAUTHORIZED,
        )

    

    if user.is_staff or user.is_superuser:
        return otp_error(
            "Please use the admin login page.",
            status.HTTP_403_FORBIDDEN,
        )

    if not user.is_active:
        return otp_error(
            "This account is inactive.",
            status.HTTP_403_FORBIDDEN,
        )

    if not user.is_email_verified:
        return otp_error(
            "Please verify your email first.",
            status.HTTP_403_FORBIDDEN,
        )

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "message": "User login successful.",
             "access": str(refresh.access_token),
             "refresh": str(refresh),
            "user": {
                "user_id": user.pk,
                "full_name": user.full_name,
                "email": user.email,
                "phone_number": user.phone_number,
            },
        },
        status=status.HTTP_200_OK,
    )


# -------------------- ADMIN LOGIN --------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login(request):
    serializer = LoginSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = serializer.validated_data["email"]
    password = serializer.validated_data["password"]

    user = authenticate(
        request,
        username=email,
        password=password,
    )

    if user is None:
        return otp_error(
            "Invalid email or password.",
            status.HTTP_401_UNAUTHORIZED,
        )

    if not (user.is_staff or user.is_superuser):
        return otp_error(
            "Admin access only.",
            status.HTTP_403_FORBIDDEN,
        )

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "message": "Admin login successful.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
           "user": {
    "user_id": user.pk,
    "full_name": user.full_name,
    "email": user.email,
    "is_staff": user.is_staff,
    "is_superuser": user.is_superuser,
},
        },
        status=status.HTTP_200_OK,
    )


# -------------------- PASSWORD RESET OTP --------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def send_password_reset_otp(request):
    email = get_text(request.data, "email").lower()

    if not email:
        return otp_error("Email is required.")

    user = User.objects.filter(
        email__iexact=email,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    ).first()

    if user is None:
        return Response(
            {
                "message": (
                    "If an account exists, "
                    "a reset code will be sent."
                )
            },
            status=status.HTTP_200_OK,
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"

    PasswordResetOTP.objects.update_or_create(
        email=user.email,
        defaults={
            "otp_hash": make_password(otp),
            "expires_at": timezone.now() + timedelta(minutes=5),
            "attempts": 0,
        },
    )

    try:
        send_rentbee_otp_email(
            to_email=user.email,
            otp=otp,
            purpose=OTP_PURPOSE_PASSWORD_RESET,
            expiry_minutes=5,
        )
    except Exception:
        PasswordResetOTP.objects.filter(
            email__iexact=user.email
        ).delete()

        return Response(
            {
                "error": (
                    "Could not send the email. Please try again."
                )
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            "message": (
                "If an account exists, "
                "a reset code will be sent."
            )
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_password_reset_otp(request):
    email = get_text(request.data, "email").lower()
    otp = get_text(request.data, "otp")

    if not email or not otp:
        return otp_error("Email and OTP are required.")

    reset_request = PasswordResetOTP.objects.filter(
        email__iexact=email
    ).first()

    if reset_request is None:
        return otp_error(
            "Invalid or expired reset code. Request a new one."
        )

    if timezone.now() >= reset_request.expires_at:
        reset_request.delete()
        return otp_error("Reset code expired. Request a new one.")

    if reset_request.attempts >= 5:
        reset_request.delete()
        return otp_error(
            "Too many attempts. Request a new code.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    reset_request.attempts += 1
    reset_request.save(update_fields=["attempts"])

    if not check_password(otp, reset_request.otp_hash):
        if reset_request.attempts >= 5:
            reset_request.delete()
            return otp_error(
                "Too many attempts. Request a new code.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        return otp_error("Invalid reset code.")

    user_exists = User.objects.filter(
        email__iexact=email,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    ).exists()

    if not user_exists:
        reset_request.delete()
        return otp_error("Unable to verify this reset request.")

    reset_token = secrets.token_urlsafe(32)

    reset_request.otp_hash = make_password("RESET:" + reset_token)
    reset_request.expires_at = timezone.now() + timedelta(minutes=5)
    reset_request.attempts = 0
    reset_request.save(
        update_fields=["otp_hash", "expires_at", "attempts"]
    )

    return Response(
        {
            "message": "OTP verified. You can now reset your password.",
            "reset_token": reset_token,
        },
        status=status.HTTP_200_OK,
    )



@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password_with_otp(request):
    email = get_text(request.data, "email").lower()
    reset_token = get_text(request.data, "reset_token")
    new_password = request.data.get("new_password", "")

    if not isinstance(new_password, str):
        new_password = ""

    if not email or not reset_token or not new_password:
        return otp_error(
            "Email, reset token and new password are required."
        )

    reset_request = PasswordResetOTP.objects.filter(
        email__iexact=email
    ).first()

    if reset_request is None:
        return otp_error(
            "Invalid or expired reset token. Verify OTP again."
        )

    if timezone.now() >= reset_request.expires_at:
        reset_request.delete()
        return otp_error("Reset token expired. Request a new OTP.")

    if not check_password(
        "RESET:" + reset_token,
        reset_request.otp_hash,
    ):
        return otp_error(
            "Invalid reset token. Verify OTP again."
        )

    user = User.objects.filter(
        email__iexact=email,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    ).first()

    if user is None:
        reset_request.delete()
        return otp_error("Unable to reset this password.")

    try:
        validate_password(new_password, user=user)
    except ValidationError as error:
        return Response(
            {"error": list(error.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    for outstanding_token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(
            token=outstanding_token
        )

    reset_request.delete()

    return Response(
        {
            "message": "Password reset successful. Please log in again."
        },
        status=status.HTTP_200_OK,
    )
# -------------------- LOGOUT --------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def logout(request):

    refresh_token = request.data.get("refresh")

    if not refresh_token:
        return Response(
            {"error": "Refresh token is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()

    except TokenError:
        return Response(
            {"error": "Invalid or expired refresh token."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {"message": "Logout successful."},
        status=status.HTTP_200_OK,
    )


# -------------------- USER PROFILE --------------------

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsActiveUser])
def user_profile(request):

    profile, _ = Profile.objects.get_or_create(
        user=request.user
    )

    if request.method == "GET":
        serializer = ProfileSerializer(profile)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    elif request.method == "PATCH":
        serializer = ProfileSerializer(
            profile,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )



@api_view(["POST"])
@permission_classes([IsAuthenticated, IsActiveUser])
def send_email_change_otp(request):
    new_email = request.data.get("email", "").strip().lower()

    if not new_email:
        return Response(
            {"error": "Email address is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        validate_email(new_email)
    except ValidationError:
        return Response(
            {"error": "Enter a valid email address."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email__iexact=new_email).exists():
        return Response(
            {"error": "This email is already registered."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if new_email == request.user.email.lower():
        return Response(
            {"error": "This is already your current email."},
            status=status.HTTP_400_BAD_REQUEST
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"

    EmailChangeOTP.objects.update_or_create(
        user=request.user,
        defaults={
            "new_email": new_email,
            "otp_hash": make_password(otp),
            "expires_at": timezone.now() + timedelta(minutes=5),
            "attempts": 0,
        }
    )

    try:
        send_rentbee_otp_email(
            to_email=new_email,
            otp=otp,
            purpose=OTP_PURPOSE_EMAIL_CHANGE,
            expiry_minutes=5,
        )

    except Exception:
        EmailChangeOTP.objects.filter(user=request.user).delete()

        return Response(
            {"error": "Unable to send OTP. Please try again."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return Response(
        {"message": "OTP sent to your new email address."},
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated ,  IsActiveUser])
def verify_email_change_otp(request):
    otp = request.data.get("otp", "").strip()

    if not otp:
        return Response(
            {"error": "OTP is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not otp.isdigit() or len(otp) != 6:
        return Response(
            {"error": "Enter a valid 6-digit OTP."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        email_otp = EmailChangeOTP.objects.get(user=request.user)
    except EmailChangeOTP.DoesNotExist:
        return Response(
            {"error": "Please request an email verification OTP first."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if timezone.now() > email_otp.expires_at:
        email_otp.delete()
        return Response(
            {"error": "OTP has expired. Please request a new OTP."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if email_otp.attempts >= 5:
        email_otp.delete()
        return Response(
            {"error": "Too many attempts. Please request a new OTP."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not check_password(otp, email_otp.otp_hash):
        email_otp.attempts += 1

        if email_otp.attempts >= 5:
            email_otp.delete()
            return Response(
                {"error": "Too many attempts. Please request a new OTP."},
                status=status.HTTP_400_BAD_REQUEST
            )

        email_otp.save(update_fields=["attempts"])

        return Response(
            {"error": "Invalid OTP."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(
        email__iexact=email_otp.new_email
    ).exclude(pk=request.user.pk).exists():
        email_otp.delete()
        return Response(
            {"error": "This email is already registered."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user
    user.email = email_otp.new_email
    user.is_email_verified = True
    user.save(update_fields=["email", "is_email_verified"])

    email_otp.delete()

    return Response(
        {"message": "Email address updated and verified successfully."},
        status=status.HTTP_200_OK
    )
@api_view(["POST"])
@permission_classes([IsAuthenticated ,  IsActiveUser])
def change_password(request):

    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")
    confirm_password = request.data.get("confirm_password")

    if not current_password or not new_password or not confirm_password:
        return Response(
            {"error": "All fields are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user

    if not user.check_password(current_password):
        return Response(
            {"error": "Current password is incorrect."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if new_password != confirm_password:
        return Response(
            {"error": "New passwords do not match."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if current_password == new_password:
        return Response(
            {"error": "New password must be different from current password."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        validate_password(new_password, user)
    except ValidationError as error:
        return Response(
            {"error": list(error.messages)},
            status=status.HTTP_400_BAD_REQUEST
        )

    
    user.set_password(new_password)
    user.save(update_fields=["password"])

    for outstanding_token in OutstandingToken.objects.filter(user=user):
      BlacklistedToken.objects.get_or_create(
        token=outstanding_token
    )

    return Response(
      {"message": "Password changed successfully."},
    status=status.HTTP_200_OK
)