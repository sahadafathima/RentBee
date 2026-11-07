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
