import io
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from .image_utils import process_item_image, validate_image_file
from .models import Category, Item

User = get_user_model()


class PillowImageProcessingTests(TestCase):
    def test_process_item_image_resizes_and_compresses(self):
        # Create an oversized test image (2400x1800)
        img = Image.new('RGB', (2400, 1800), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        uploaded = SimpleUploadedFile("camera_hd.jpg", buf.getvalue(), content_type="image/jpeg")

        processed = process_item_image(uploaded, max_width=1200, max_height=900, quality=85)

        # Inspect resulting image with Pillow
        result_img = Image.open(processed.file)
        # Dimensions must not exceed 1200x900
        self.assertLessEqual(result_img.width, 1200)
        self.assertLessEqual(result_img.height, 900)
        # 2400x1800 has 4:3 aspect ratio, so thumbnail must be exactly 1200x900
        self.assertEqual(result_img.size, (1200, 900))
        # Compressed file size must be well under 500KB
        self.assertLess(processed.size, 500 * 1024)

    def test_invalid_image_extension_rejected(self):
        invalid_file = SimpleUploadedFile("document.txt", b"not an image", content_type="text/plain")
        with self.assertRaises(ValidationError):
            validate_image_file(invalid_file)


class CategoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(email="admin@rentbee.com", password="p", full_name="Admin", phone_number="1", is_staff=True)
        self.user = User.objects.create_user(email="user@rentbee.com", password="p", full_name="User", phone_number="2", is_staff=False)

    def test_non_admin_gets_403(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get("/api/admin/categories/").status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_category(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/categories/", {"name": "Tools", "icon": "🔧"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["slug"], "tools")

    def test_duplicate_icon_rejected_for_active_category(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/categories/", {"name": "Tools", "icon": "🔧"}, format="json")
        res = self.client.post("/api/admin/categories/", {"name": "Repairs", "icon": "🔧"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("icon", res.data)

    def test_soft_delete_releases_icon(self):
        self.client.force_authenticate(user=self.admin)
        create_res = self.client.post("/api/admin/categories/", {"name": "Camping", "icon": "⛺"}, format="json")
        cat_id = create_res.data["id"]
        del_res = self.client.post(f"/api/admin/categories/{cat_id}/delete/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        new_res = self.client.post("/api/admin/categories/", {"name": "Outdoor", "icon": "⛺"}, format="json")
        self.assertEqual(new_res.status_code, status.HTTP_201_CREATED)

    def test_category_items_count_updates_accurately(self):
        self.client.force_authenticate(user=self.admin)
        cat_tools = Category.objects.create(name="Tools", icon="🔧", is_active=True)
        cat_cameras = Category.objects.create(name="Cameras", icon="📷", is_active=True)

        # Initially 0 items
        res = self.client.get("/api/admin/categories/")
        tools_data = next(c for c in res.data["results"] if c["id"] == cat_tools.id)
        cameras_data = next(c for c in res.data["results"] if c["id"] == cat_cameras.id)
        self.assertEqual(tools_data["items_count"], 0)
        self.assertEqual(cameras_data["items_count"], 0)

        # 1. Add item to Tools
        item = Item.objects.create(
            name="Cordless Drill",
            category=cat_tools,
            rental_price=100.0,
            stock=1,
            is_published=True
        )

        res = self.client.get("/api/admin/categories/")
        tools_data = next(c for c in res.data["results"] if c["id"] == cat_tools.id)
        cameras_data = next(c for c in res.data["results"] if c["id"] == cat_cameras.id)
        self.assertEqual(tools_data["items_count"], 1)
        self.assertEqual(cameras_data["items_count"], 0)

        # 2. Change category from Tools to Cameras
        patch_res = self.client.patch(f"/api/admin/items/{item.id}/", {"category_id": cat_cameras.id}, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)

        res = self.client.get("/api/admin/categories/")
        tools_data = next(c for c in res.data["results"] if c["id"] == cat_tools.id)
        cameras_data = next(c for c in res.data["results"] if c["id"] == cat_cameras.id)
        self.assertEqual(tools_data["items_count"], 0)
        self.assertEqual(cameras_data["items_count"], 1)

        # 3. Soft-delete the item
        del_res = self.client.post(f"/api/admin/items/{item.id}/delete/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)

        res = self.client.get("/api/admin/categories/")
        tools_data = next(c for c in res.data["results"] if c["id"] == cat_tools.id)
        cameras_data = next(c for c in res.data["results"] if c["id"] == cat_cameras.id)
        self.assertEqual(tools_data["items_count"], 0)
        self.assertEqual(cameras_data["items_count"], 0)

    def test_public_category_list_ordering_preserves_order_and_appends_new_at_end(self):
        """
        Customer-facing /api/categories/ must:
        1. Keep all existing categories in chronological creation order.
        2. Append newly created categories at the END of the list, regardless of alphabetical naming.
        """
        # Create categories in a specific order: Cameras first, then Tools
        cat1 = Category.objects.create(name="Cameras", icon="📷", is_active=True)
        cat2 = Category.objects.create(name="Tools", icon="🔧", is_active=True)

        res = self.client.get("/api/categories/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [c["id"] for c in res.data]
        self.assertEqual(ids, [cat1.id, cat2.id])

        # Create a new category that begins with 'A' (e.g. "Audio Gear")
        # Alphabetically this would jump to index 0, but it must be placed at the END.
        cat3 = Category.objects.create(name="Audio Gear", icon="🎧", is_active=True)

        res2 = self.client.get("/api/categories/")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        ids2 = [c["id"] for c in res2.data]
        # Must preserve cat1, cat2 and append cat3 at the END
        self.assertEqual(ids2, [cat1.id, cat2.id, cat3.id])
        self.assertEqual(res2.data[-1]["id"], cat3.id)
        self.assertEqual(res2.data[-1]["name"], "Audio Gear")


class ItemDepositTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(email="admin_dep@rentbee.com", password="p", full_name="Admin", phone_number="9991", is_staff=True)
        self.user = User.objects.create_user(email="user_dep@rentbee.com", password="p", full_name="User", phone_number="9992", is_staff=False)
        self.category = Category.objects.create(name="Electronics", icon="🎧", is_active=True)

    def test_admin_create_item_with_deposit(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/items/", {
            "name": "Sony Headphones",
            "category_id": self.category.id,
            "rental_price": "250.00",
            "deposit": "1000.00",
            "stock": 2,
        }, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(res.data["deposit"]), 1000.00)

        item = Item.objects.get(id=res.data["id"])
        self.assertEqual(float(item.deposit), 1000.00)

    def test_admin_create_item_with_empty_deposit_defaults_to_zero(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/items/", {
            "name": "Tripod",
            "category_id": self.category.id,
            "rental_price": "100.00",
            "deposit": "",
            "stock": 1,
        }, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(res.data["deposit"]), 0.00)

    def test_admin_create_item_without_deposit_field_defaults_to_zero(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/items/", {
            "name": "Tripod 2",
            "category_id": self.category.id,
            "rental_price": "100.00",
            "stock": 1,
        }, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(res.data["deposit"]), 0.00)

    def test_negative_deposit_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/items/", {
            "name": "Flash Drive",
            "category_id": self.category.id,
            "rental_price": "50.00",
            "deposit": "-10.00",
            "stock": 1,
        }, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("deposit", res.data)

    def test_admin_update_item_deposit(self):
        self.client.force_authenticate(user=self.admin)
        item = Item.objects.create(
            name="DSLR Camera",
            category=self.category,
            rental_price=500.00,
            deposit=1500.00,
            stock=1,
            is_published=True
        )
        res = self.client.patch(f"/api/admin/items/{item.id}/", {
            "deposit": "2000.00"
        }, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res.data["deposit"]), 2000.00)
        item.refresh_from_db()
        self.assertEqual(float(item.deposit), 2000.00)

    def test_public_item_includes_deposit(self):
        item = Item.objects.create(
            name="Ring Light",
            category=self.category,
            rental_price=150.00,
            deposit=500.00,
            stock=1,
            is_published=True
        )
        res = self.client.get("/api/items/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        item_data = next((i for i in res.data["results"] if i["id"] == item.id), None)
        self.assertIsNotNone(item_data)
        self.assertEqual(float(item_data["deposit"]), 500.00)

    def test_category_id_included_in_admin_item_serialization(self):
        self.client.force_authenticate(user=self.admin)
        item = Item.objects.create(
            name="Zoom Lens",
            category=self.category,
            rental_price=300.00,
            deposit=800.00,
            stock=1
        )
        res = self.client.get(f"/api/admin/items/{item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("category_id", res.data)
        self.assertEqual(res.data["category_id"], self.category.id)

    def test_partial_update_without_deposit_preserves_existing_deposit(self):
        self.client.force_authenticate(user=self.admin)
        item = Item.objects.create(
            name="Drone 4K",
            category=self.category,
            rental_price=800.00,
            deposit=1500.00,
            stock=1
        )
        res = self.client.patch(f"/api/admin/items/{item.id}/", {
            "name": "Drone 4K Pro"
        }, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.name, "Drone 4K Pro")
        self.assertEqual(float(item.deposit), 1500.00)
        self.assertEqual(item.category_id, self.category.id)

    def test_partial_update_with_empty_deposit_sets_zero(self):
        self.client.force_authenticate(user=self.admin)
        item = Item.objects.create(
            name="Projector HD",
            category=self.category,
            rental_price=400.00,
            deposit=1200.00,
            stock=1
        )
        res = self.client.patch(f"/api/admin/items/{item.id}/", {
            "deposit": ""
        }, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(float(item.deposit), 0.00)


class PublicItemBrowsingAndDetailsTests(TestCase):
    def setUp(self):
        from addresses.models import Address
        self.client = APIClient()
        self.category = Category.objects.create(name="Outdoor", icon="⛺", is_active=True)
        self.owner = User.objects.create_user(
            email="owner@rentbee.com",
            password="p",
            full_name="Alice Lender",
            phone_number="9876543210",
            is_active=True
        )
        self.address = Address.objects.create(
            user=self.owner,
            full_name="Alice Lender",
            address="123 Private Street Lane",
            house_number="A-402",
            area="Koramangala",
            landmark="Near Sony World Signal",
            city="Bengaluru",
            state="Karnataka",
            pincode="560034",
            address_type="Home"
        )
        self.item1 = Item.objects.create(
            name="Camping Tent 4-Person",
            category=self.category,
            owner=self.owner,
            rental_price=300.00,
            deposit=1000.00,
            stock=2,
            is_published=True
        )
        self.item2 = Item.objects.create(
            name="Sleeping Bag Thermal",
            category=self.category,
            owner=self.owner,
            rental_price=100.00,
            deposit=400.00,
            stock=0,  # Out of stock / booked
            is_published=True
        )
        self.item3 = Item.objects.create(
            name="Camp Stove Gas",
            category=self.category,
            owner=self.owner,
            rental_price=500.00,
            deposit=1500.00,
            stock=1,
            is_published=True
        )

    def test_min_and_max_price_filtering(self):
        # min_price 200
        res = self.client.get("/api/items/?min_price=200")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in res.data["results"]]
        self.assertIn(self.item1.id, ids)
        self.assertIn(self.item3.id, ids)
        self.assertNotIn(self.item2.id, ids)

        # max_price 350
        res = self.client.get("/api/items/?max_price=350")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in res.data["results"]]
        self.assertIn(self.item1.id, ids)
        self.assertIn(self.item2.id, ids)
        self.assertNotIn(self.item3.id, ids)

        # price range 150 - 400
        res = self.client.get("/api/items/?min_price=150&max_price=400")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in res.data["results"]]
        self.assertEqual(ids, [self.item1.id])

    def test_sorting_options(self):
        # Price: Low to High
        res = self.client.get("/api/items/?sort=rental_price")
        prices = [float(i["rental_price"]) for i in res.data["results"]]
        self.assertEqual(prices, sorted(prices))

        # Price: High to Low
        res = self.client.get("/api/items/?sort=-rental_price")
        prices = [float(i["rental_price"]) for i in res.data["results"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_owner_and_exclude_filtering(self):
        # Exclude item1
        res = self.client.get(f"/api/items/?exclude={self.item1.id}")
        ids = [i["id"] for i in res.data["results"]]
        self.assertNotIn(self.item1.id, ids)

        # Filter by owner
        res = self.client.get(f"/api/items/?owner={self.owner.id}")
        self.assertEqual(len(res.data["results"]), 3)

    def test_availability_and_safe_owner_details(self):
        # Available item (stock > 0)
        res = self.client.get(f"/api/items/{self.item1.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_available"])
        self.assertEqual(res.data["stock"], 2)

        # Booked item (stock == 0)
        res2 = self.client.get(f"/api/items/{self.item2.id}/")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertFalse(res2.data["is_available"])
        self.assertEqual(res2.data["stock"], 0)

        # Privacy verification on owner details:
        owner_details = res.data["owner_details"]
        self.assertEqual(owner_details["name"], "Alice Lender")
        self.assertEqual(owner_details["locality"], "Koramangala")
        self.assertEqual(owner_details["nearest_location"], "Near Sony World Signal")
        self.assertEqual(owner_details["city"], "Bengaluru")
        self.assertEqual(owner_details["state"], "Karnataka")
        # Ensure private fields are NOT exposed
        self.assertNotIn("123 Private Street Lane", str(res.data))
        self.assertNotIn("A-402", str(res.data))
        self.assertNotIn("9876543210", str(res.data))
        self.assertNotIn("owner@rentbee.com", str(res.data))


class RentalKitTests(TestCase):
    def setUp(self):
        import json
        from .models import RentalKitItem
        self.json = json
        self.RentalKitItem = RentalKitItem
        self.client = APIClient()
        self.admin = User.objects.create_user(email="admin_kit@rentbee.com", password="p", full_name="Admin", phone_number="123450", is_staff=True)
        self.category = Category.objects.create(name="Cameras", icon="📷", is_active=True)

    def test_admin_create_item_with_rental_kit(self):
        self.client.force_authenticate(user=self.admin)
        kit_items = ["24-70mm Lens", "Dual Battery Charger", "Camera Strap"]
        res = self.client.post("/api/admin/items/", {
            "name": "Canon EOS R5",
            "category_id": self.category.id,
            "rental_price": "800.00",
            "deposit": "2000.00",
            "stock": 2,
            "rental_kit": self.json.dumps(kit_items)
        }, format="multipart")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        item_id = res.data["id"]
        item = Item.objects.get(id=item_id)
        saved_kit = list(item.rental_kit_items.values_list('name', flat=True))
        self.assertEqual(saved_kit, kit_items)
        self.assertEqual(res.data["rental_kit"], kit_items)

    def test_admin_create_item_without_rental_kit_empty_list(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/items/", {
            "name": "Standard Monopod",
            "category_id": self.category.id,
            "rental_price": "150.00",
            "stock": 3,
        }, format="multipart")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["rental_kit"], [])

    def test_admin_update_rental_kit_entries(self):
        self.client.force_authenticate(user=self.admin)
        # Create item with 2 accessories
        item = Item.objects.create(
            name="Sony A7 IV",
            category=self.category,
            rental_price=600.00,
            stock=1
        )
        self.RentalKitItem.objects.create(item=item, name="50mm F1.8 Lens")
        self.RentalKitItem.objects.create(item=item, name="Battery")

        # Update with new list (edit entry, remove one, add one)
        new_kit = ["85mm F1.4 GM Lens", "Carrying Case", "Sandisk 128GB SD Card"]
        res = self.client.patch(f"/api/admin/items/{item.id}/", {
            "rental_kit": self.json.dumps(new_kit)
        }, format="multipart")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rental_kit"], new_kit)
        updated_kit = list(item.rental_kit_items.values_list('name', flat=True))
        self.assertEqual(updated_kit, new_kit)

    def test_update_other_item_detail_preserves_rental_kit(self):
        self.client.force_authenticate(user=self.admin)
        item = Item.objects.create(
            name="DJI RS 3 Gimbal",
            category=self.category,
            rental_price=450.00,
            stock=1
        )
        self.RentalKitItem.objects.create(item=item, name="Briefcase Handle")
        self.RentalKitItem.objects.create(item=item, name="Focus Motor")

        # Update only price, do NOT send rental_kit
        res = self.client.patch(f"/api/admin/items/{item.id}/", {
            "rental_price": "500.00"
        }, format="multipart")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Existing kit items MUST be preserved
        self.assertEqual(res.data["rental_kit"], ["Briefcase Handle", "Focus Motor"])
        self.assertEqual(item.rental_kit_items.count(), 2)

    def test_public_item_detail_includes_rental_kit(self):
        item = Item.objects.create(
            name="GoPro Hero 11",
            category=self.category,
            rental_price=350.00,
            stock=1,
            is_published=True
        )
        self.RentalKitItem.objects.create(item=item, name="Waterproof Case")
        self.RentalKitItem.objects.create(item=item, name="Floating Hand Grip")

        res = self.client.get(f"/api/items/{item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rental_kit"], ["Waterproof Case", "Floating Hand Grip"])

    def test_rental_kit_items_isolation_between_items(self):
        item_a = Item.objects.create(
            name="Camera A",
            category=self.category,
            rental_price=300.00,
            stock=1,
            is_published=True
        )
        item_b = Item.objects.create(
            name="Camera B",
            category=self.category,
            rental_price=400.00,
            stock=1,
            is_published=True
        )
        self.RentalKitItem.objects.create(item=item_a, name="Lens A")
        self.RentalKitItem.objects.create(item=item_b, name="Lens B")

        res_a = self.client.get(f"/api/items/{item_a.id}/")
        res_b = self.client.get(f"/api/items/{item_b.id}/")

        self.assertEqual(res_a.data["rental_kit"], ["Lens A"])
        self.assertEqual(res_b.data["rental_kit"], ["Lens B"])
        self.assertNotIn("Lens B", res_a.data["rental_kit"])
        self.assertNotIn("Lens A", res_b.data["rental_kit"])

    def test_admin_update_rental_kit_via_json(self):
        self.client.force_authenticate(user=self.admin)
        item = Item.objects.create(
            name="Tripod Kit",
            category=self.category,
            rental_price=100.00,
            stock=2
        )
        res = self.client.patch(
            f"/api/admin/items/{item.id}/",
            {"rental_kit": ["Quick Release Plate", "Carrying Bag"]},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rental_kit"], ["Quick Release Plate", "Carrying Bag"])





