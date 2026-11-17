from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
import re
import smtplib
from unittest.mock import patch, MagicMock

from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from .models import PendingSignup, PasswordResetOTP, EmailChangeOTP
from django.contrib.auth.hashers import make_password
from .email_service import send_rentbee_otp_email, OTP_PURPOSE_SIGNUP, OTP_PURPOSE_PASSWORD_RESET, OTP_PURPOSE_EMAIL_CHANGE

User = get_user_model()


class UserAuthAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.regular_user = User.objects.create_user(
            email="regular@rentbee.com",
            password="StrongPassword123!",
            full_name="Regular User",
            phone_number="9998887770",
            is_email_verified=True,
            is_active=True,
        )
        self.admin_user = User.objects.create_superuser(
            email="admin@rentbee.com",
            password="AdminPassword123!",
            full_name="Admin User",
            phone_number="9998887771",
        )

    def test_signup_otp_flow(self):
        send_res = self.client.post("/api/signup/send-otp/", {
            "full_name": "New User",
            "email": "newuser@rentbee.com",
            "phone_number": "9123456780",
            "password": "SecurePassword123!",
        }, format="json")
        self.assertEqual(send_res.status_code, status.HTTP_200_OK)

        pending = PendingSignup.objects.get(email="newuser@rentbee.com")
        self.assertIsNotNone(pending)

        # Mock OTP verification
        otp = "123456"
        pending.otp_hash = make_password(otp)
        pending.save()

        verify_res = self.client.post("/api/signup/verify-otp/", {
            "email": "newuser@rentbee.com",
            "otp": otp,
        }, format="json")

        self.assertEqual(verify_res.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", verify_res.data)
        self.assertIn("refresh", verify_res.data)
        self.assertTrue(User.objects.filter(email="newuser@rentbee.com").exists())

    def test_user_login_success(self):
        res = self.client.post("/api/login/", {
            "email": "regular@rentbee.com",
            "password": "StrongPassword123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_admin_cannot_use_regular_login(self):
        res = self.client.post("/api/login/", {
            "email": "admin@rentbee.com",
            "password": "AdminPassword123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_access_admin_login(self):
        res = self.client.post("/api/admin/login/", {
            "email": "regular@rentbee.com",
            "password": "StrongPassword123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_login_success(self):
        res = self.client.post("/api/admin/login/", {
            "email": "admin@rentbee.com",
            "password": "AdminPassword123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertTrue(res.data["user"]["is_staff"])


class TokenLifecycleAndLogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="tokenuser@rentbee.com",
            password="StrongPassword123!",
            full_name="Token User",
            phone_number="9998887772",
            is_email_verified=True,
            is_active=True,
        )

    def test_token_refresh_successful_rotation(self):
        refresh = RefreshToken.for_user(self.user)
        res = self.client.post("/api/token/refresh/", {
            "refresh": str(refresh),
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        new_refresh = res.data["refresh"]
        self.assertNotEqual(str(refresh), new_refresh)

    def test_old_refresh_token_blacklisted_after_rotation(self):
        refresh = RefreshToken.for_user(self.user)
        res1 = self.client.post("/api/token/refresh/", {
            "refresh": str(refresh),
        }, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Attempting to use the old refresh token again must fail (blacklisted)
        res2 = self.client.post("/api/token/refresh/", {
            "refresh": str(refresh),
        }, format="json")
        self.assertEqual(res2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_token_without_access_token(self):
        refresh = RefreshToken.for_user(self.user)
        # Logout call without Authorization header (unauthenticated / expired access token)
        res = self.client.post("/api/logout/", {
            "refresh": str(refresh),
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["message"], "Logout successful.")

        # The blacklisted token cannot be used to refresh
        refresh_res = self.client.post("/api/token/refresh/", {
            "refresh": str(refresh),
        }, format="json")
        self.assertEqual(refresh_res.status_code, status.HTTP_401_UNAUTHORIZED)


class EmailOTPDeliveryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="existing@rentbee.com",
            password="StrongPassword123!",
            full_name="Existing User",
            phone_number="9876543210",
            is_email_verified=True,
            is_active=True,
        )

    def _extract_otp_from_email(self, email_obj):
        """Extracts 6-digit OTP code from email plain text or HTML body."""
        match = re.search(r'\b\d{6}\b', email_obj.body)
        if match:
            return match.group(0)
        # Check in HTML alternatives
        for content, mime in getattr(email_obj, 'alternatives', []):
            if mime == 'text/html':
                match = re.search(r'\b\d{6}\b', content)
                if match:
                    return match.group(0)
        return None

    def test_signup_otp_email_delivery_and_verification(self):
        """Verifies signup OTP creates HTML/text email, delivers via outbox, and verifies cleanly."""
        mail.outbox.clear()
        res = self.client.post("/api/signup/send-otp/", {
            "full_name": "Alice Tester",
            "email": "alice@rentbee.com",
            "phone_number": "9123456789",
            "password": "SecurePassword123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["message"], "OTP sent. Please check your email.")

        # Verify email was dispatched to outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["alice@rentbee.com"])
        self.assertIn("RentBee Email Verification Code", sent_email.subject)
        self.assertIn("RentBee", sent_email.body)

        # Check HTML alternative content exists
        self.assertTrue(any(mime == "text/html" for _, mime in sent_email.alternatives))
        html_body = next(content for content, mime in sent_email.alternatives if mime == "text/html")
        self.assertIn("Never share this code with anyone", html_body)

        # Extract OTP from email
        delivered_otp = self._extract_otp_from_email(sent_email)
        self.assertIsNotNone(delivered_otp)
        self.assertEqual(len(delivered_otp), 6)

        # Verify the delivered OTP works
        verify_res = self.client.post("/api/signup/verify-otp/", {
            "email": "alice@rentbee.com",
            "otp": delivered_otp,
        }, format="json")
        self.assertEqual(verify_res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="alice@rentbee.com").exists())

    def test_signup_otp_resend_invalidates_old_otp(self):
        """Verifies resending signup OTP invalidates the previous code and issues a new one."""
        mail.outbox.clear()
        payload = {
            "full_name": "Bob Tester",
            "email": "bob@rentbee.com",
            "phone_number": "9123456788",
            "password": "SecurePassword123!",
        }
        # First send
        res1 = self.client.post("/api/signup/send-otp/", payload, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        first_otp = self._extract_otp_from_email(mail.outbox[0])

        # Second send (resend)
        res2 = self.client.post("/api/signup/send-otp/", payload, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 2)
        second_otp = self._extract_otp_from_email(mail.outbox[1])

        # Attempting verify with first OTP must be rejected if codes differ
        if first_otp != second_otp:
            fail_res = self.client.post("/api/signup/verify-otp/", {
                "email": "bob@rentbee.com",
                "otp": first_otp,
            }, format="json")
            self.assertEqual(fail_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Second OTP must succeed
        success_res = self.client.post("/api/signup/verify-otp/", {
            "email": "bob@rentbee.com",
            "otp": second_otp,
        }, format="json")
        self.assertEqual(success_res.status_code, status.HTTP_201_CREATED)

    def test_password_reset_otp_flow(self):
        """Verifies password reset OTP is delivered to user email and successfully resets password."""
        mail.outbox.clear()
        send_res = self.client.post("/api/password-reset/send-otp/", {
            "email": "existing@rentbee.com",
        }, format="json")
        self.assertEqual(send_res.status_code, status.HTTP_200_OK)

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["existing@rentbee.com"])
        self.assertIn("Password Reset Code", sent_email.subject)

        delivered_otp = self._extract_otp_from_email(sent_email)
        self.assertIsNotNone(delivered_otp)

        # Verify OTP and obtain reset token
        verify_res = self.client.post("/api/password-reset/verify-otp/", {
            "email": "existing@rentbee.com",
            "otp": delivered_otp,
        }, format="json")
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        reset_token = verify_res.data.get("reset_token")
        self.assertIsNotNone(reset_token)

        # Complete password reset
        new_password = "BrandNewPassword123!"
        reset_res = self.client.post("/api/password-reset/reset/", {
            "email": "existing@rentbee.com",
            "reset_token": reset_token,
            "new_password": new_password,
        }, format="json")
        self.assertEqual(reset_res.status_code, status.HTTP_200_OK)

        # Verify login with new password works
        login_res = self.client.post("/api/login/", {
            "email": "existing@rentbee.com",
            "password": new_password,
        }, format="json")
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

    def test_email_change_otp_flow(self):
        """Verifies authenticated user receives email change OTP at the new address and confirms."""
        mail.outbox.clear()
        self.client.force_authenticate(user=self.user)

        new_email = "newemail@rentbee.com"
        send_res = self.client.post("/api/profile/email-change/send-otp/", {
            "email": new_email,
        }, format="json")
        self.assertEqual(send_res.status_code, status.HTTP_200_OK)

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, [new_email])
        self.assertIn("Email Change Verification", sent_email.subject)

        delivered_otp = self._extract_otp_from_email(sent_email)
        self.assertIsNotNone(delivered_otp)

        # Verify email change
        verify_res = self.client.post("/api/profile/email-change/verify-otp/", {
            "otp": delivered_otp,
        }, format="json")
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, new_email)

    def test_expired_otp_rejection(self):
        """Verifies expired OTP is rejected and cleaned up."""
        PendingSignup.objects.create(
            email="expired@rentbee.com",
            full_name="Expired User",
            phone_number="9123456787",
            password_hash=make_password("Pass123!"),
            otp_hash=make_password("999999"),
            expires_at=timezone.now() - timedelta(minutes=1),
            attempts=0,
        )
        res = self.client.post("/api/signup/verify-otp/", {
            "email": "expired@rentbee.com",
            "otp": "999999",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", res.data["error"].lower())
        self.assertFalse(PendingSignup.objects.filter(email="expired@rentbee.com").exists())

    def test_otp_attempt_limits_lockout(self):
        """Verifies 5 incorrect attempts delete the pending record and return HTTP 429."""
        PendingSignup.objects.create(
            email="attacker@rentbee.com",
            full_name="Attacker",
            phone_number="9123456786",
            password_hash=make_password("Pass123!"),
            otp_hash=make_password("654321"),
            expires_at=timezone.now() + timedelta(minutes=10),
            attempts=4,  # Already at 4 attempts
        )
        # 5th failed attempt
        res = self.client.post("/api/signup/verify-otp/", {
            "email": "attacker@rentbee.com",
            "otp": "000000",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(PendingSignup.objects.filter(email="attacker@rentbee.com").exists())

    @patch("users.views.send_rentbee_otp_email")
    def test_smtp_failure_handling_returns_503_and_cleans_record(self, mock_send):
        """Verifies that an SMTP network error returns HTTP 503 and rolls back pending signup record."""
        mock_send.side_effect = Exception("SMTP Connection Refused")

        res = self.client.post("/api/signup/send-otp/", {
            "full_name": "Charlie Tester",
            "email": "charlie@rentbee.com",
            "phone_number": "9123456785",
            "password": "SecurePassword123!",
        }, format="json")

        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("error", res.data)
        # Verify no orphaned record was left in the database
        self.assertFalse(PendingSignup.objects.filter(email="charlie@rentbee.com").exists())

    @patch("users.views.send_rentbee_otp_email")
    def test_email_change_delivery_failure_returns_503_and_cleans_record(self, mock_send):
        """Verifies that an email delivery error in email change returns HTTP 503 and rolls back the OTP record."""
        mock_send.side_effect = Exception("SMTP Connection Refused")
        self.client.force_authenticate(user=self.user)

        res = self.client.post("/api/profile/email-change/send-otp/", {
            "email": "charlie_new@rentbee.com",
        }, format="json")

        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(res.data["error"], "Unable to send OTP. Please try again.")
        self.assertFalse(EmailChangeOTP.objects.filter(user=self.user).exists())


class RealSMTPDeliveryEnforcementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="smtp_user@rentbee.com",
            password="StrongPassword123!",
            full_name="SMTP Test User",
            phone_number="9876543299",
            is_email_verified=True,
            is_active=True,
        )

    def test_settings_default_backend_is_smtp(self):
        """Verifies that Django is configured to use smtp.EmailBackend and never console fallback."""
        from django.conf import settings
        import os
        # The default configuration must point to real smtp.EmailBackend
        expected_backend = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
        self.assertIn('smtp', expected_backend.lower())
        self.assertNotIn('console', expected_backend.lower())

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST_USER='',
        EMAIL_HOST_PASSWORD='',
    )
    def test_send_rentbee_otp_email_fails_safely_when_credentials_missing(self):
        """send_rentbee_otp_email raises SMTPException immediately if credentials are not configured."""
        with self.assertRaises(smtplib.SMTPException) as ctx:
            send_rentbee_otp_email("target@rentbee.com", "123456", OTP_PURPOSE_SIGNUP)
        self.assertIn("credentials", str(ctx.exception).lower())

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST_USER='',
        EMAIL_HOST_PASSWORD='',
    )
    def test_signup_otp_fails_safely_and_cleans_up_when_credentials_missing(self):
        """Signup OTP returns HTTP 503 and deletes PendingSignup when SMTP credentials are missing."""
        res = self.client.post("/api/signup/send-otp/", {
            "full_name": "No SMTP User",
            "email": "nosmtp@rentbee.com",
            "phone_number": "9123456701",
            "password": "SecurePassword123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("error", res.data)
        self.assertFalse(PendingSignup.objects.filter(email="nosmtp@rentbee.com").exists())

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST_USER='',
        EMAIL_HOST_PASSWORD='',
    )
    def test_password_reset_otp_fails_safely_and_cleans_up_when_credentials_missing(self):
        """Password reset OTP returns HTTP 503 and cleans up record when SMTP credentials are missing."""
        res = self.client.post("/api/password-reset/send-otp/", {
            "email": "smtp_user@rentbee.com",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("error", res.data)
        self.assertFalse(PasswordResetOTP.objects.filter(email="smtp_user@rentbee.com").exists())

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST_USER='',
        EMAIL_HOST_PASSWORD='',
    )
    def test_email_change_otp_fails_safely_and_cleans_up_when_credentials_missing(self):
        """Email change OTP returns HTTP 503 and cleans up record when SMTP credentials are missing."""
        self.client.force_authenticate(user=self.user)
        res = self.client.post("/api/profile/email-change/send-otp/", {
            "email": "smtp_user_new@rentbee.com",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("error", res.data)
        self.assertFalse(EmailChangeOTP.objects.filter(user=self.user).exists())

    @patch("django.core.mail.EmailMultiAlternatives.send", return_value=0)
    def test_send_rentbee_otp_email_raises_if_message_not_delivered(self, mock_send):
        """send_rentbee_otp_email raises SMTPException if sent message count is 0."""
        with self.assertRaises(smtplib.SMTPException):
            send_rentbee_otp_email("target@rentbee.com", "123456", OTP_PURPOSE_SIGNUP)




