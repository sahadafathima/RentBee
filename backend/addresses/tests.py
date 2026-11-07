from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from .models import Address

User = get_user_model()


class AddressAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(
            email="user1@rentbee.com",
            password="testpassword123",
            full_name="User One",
            phone_number="9876543210",
            is_email_verified=True,
            is_active=True,
        )
        self.user2 = User.objects.create_user(
            email="user2@rentbee.com",
            password="testpassword123",
            full_name="User Two",
            phone_number="9876543211",
            is_email_verified=True,
            is_active=True,
        )

    def test_user_can_create_multiple_addresses_without_overwrite(self):
        self.client.force_authenticate(user=self.user1)

        addr1_payload = {
            "full_name": "User One Home",
            "address": "123 Main St",
            "house_number": "1A",
            "area": "Downtown",
            "landmark": "Near Park",
            "country": "India",
            "state": "Kerala",
            "city": "Kochi",
            "pincode": "682001",
            "address_type": "Home",
        }
        res1 = self.client.post("/api/addresses/", addr1_payload, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        addr2_payload = {
            "full_name": "User One Work",
            "address": "456 IT Park",
            "house_number": "Building B",
            "area": "Infopark",
            "landmark": "Gate 2",
            "country": "India",
            "state": "Kerala",
            "city": "Kochi",
            "pincode": "682042",
            "address_type": "Work",
        }
        res2 = self.client.post("/api/addresses/", addr2_payload, format="json")
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # Verify that BOTH addresses exist and were not overwritten
        list_res = self.client.get("/api/addresses/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        addresses = list_res.data if isinstance(list_res.data, list) else list_res.data.get("results", [])
        self.assertEqual(len(addresses), 2)
        self.assertEqual(Address.objects.filter(user=self.user1).count(), 2)

    def test_user_can_update_and_delete_address(self):
        self.client.force_authenticate(user=self.user1)
        addr = Address.objects.create(
            user=self.user1,
            full_name="User One",
            address="Old Address",
            house_number="1",
            area="Area",
            city="Kochi",
            state="Kerala",
            pincode="682001",
            address_type="Home",
        )

        patch_res = self.client.patch(
            f"/api/addresses/{addr.id}/",
            {"city": "Thrissur", "pincode": "680001"},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        addr.refresh_from_db()
        self.assertEqual(addr.city, "Thrissur")
        self.assertEqual(addr.pincode, "680001")

        del_res = self.client.delete(f"/api/addresses/{addr.id}/")
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Address.objects.filter(id=addr.id).exists())

    def test_user_cannot_access_other_users_address(self):
        addr_user1 = Address.objects.create(
            user=self.user1,
            full_name="User One",
            address="Private Road",
            house_number="1",
            area="Area",
            city="Kochi",
            state="Kerala",
            pincode="682001",
        )

        self.client.force_authenticate(user=self.user2)
        get_res = self.client.get(f"/api/addresses/{addr_user1.id}/")
        self.assertEqual(get_res.status_code, status.HTTP_404_NOT_FOUND)

        del_res = self.client.delete(f"/api/addresses/{addr_user1.id}/")
        self.assertEqual(del_res.status_code, status.HTTP_404_NOT_FOUND)
