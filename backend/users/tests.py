from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from .models import PendingSignup
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.hashers import make_password

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
