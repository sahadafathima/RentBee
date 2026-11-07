from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="admin@rentbee.com",
            password="AdminPassword123!",
            full_name="Admin Staff",
            phone_number="9990001110",
        )
        self.customer = User.objects.create_user(
            email="customer@rentbee.com",
            password="CustomerPassword123!",
            full_name="Customer User",
            phone_number="9990001111",
            is_active=True,
            is_email_verified=True,
        )

    def test_unauthenticated_cannot_access_admin_endpoints(self):
        res = self.client.get("/api/admin/users/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_forbidden(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.get("/api/admin/users/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_and_search_users(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/admin/users/?search=customer")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "customer@rentbee.com")

    def test_admin_can_block_and_unblock_user(self):
        self.client.force_authenticate(user=self.admin)

        # Block user
        block_res = self.client.patch(
            f"/api/admin/users/{self.customer.id}/status/",
            {"action": "block"},
            format="json",
        )
        self.assertEqual(block_res.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

        # Unblock user
        unblock_res = self.client.patch(
            f"/api/admin/users/{self.customer.id}/status/",
            {"action": "unblock"},
            format="json",
        )
        self.assertEqual(unblock_res.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
