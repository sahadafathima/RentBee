
from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path(
        "signup/send-otp/",
        views.send_signup_otp,
        name="send_signup_otp",
    ),
    path(
        "signup/verify-otp/",
        views.verify_signup_otp,
        name="verify_signup_otp",
    ),

    path("login/", views.user_login, name="user_login"),
    path(
        "login/send-otp/",
        views.send_login_otp,
        name="send_login_otp",
    ),
    path(
        "login/verify-otp/",
        views.verify_login_otp,
        name="verify_login_otp",
    ),

    path("admin/login/", views.admin_login, name="admin_login"),
    path("logout/", views.logout, name="logout"),

    path("profile/", views.user_profile, name="user_profile"),
    path(
        "profile/email-change/send-otp/",
        views.send_email_change_otp,
        name="send_email_change_otp",
    ),
    path(
        "profile/email-change/verify-otp/",
        views.verify_email_change_otp,
        name="verify_email_change_otp",
    ),

    path(
        "password-reset/send-otp/",
        views.send_password_reset_otp,
        name="send_password_reset_otp",
    ),
    path(
        "password-reset/verify-otp/",
        views.verify_password_reset_otp,
        name="verify_password_reset_otp",
    ),
    path(
        "password-reset/reset/",
        views.reset_password_with_otp,
        name="reset_password_with_otp",
    ),

    path(
        "profile/change-password/",
        views.change_password,
        name="change_password",
    ),

   path(
    "token/refresh/",
    TokenRefreshView.as_view(),
    name="token_refresh",
   ), 
]

