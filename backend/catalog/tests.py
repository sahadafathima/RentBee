import io
from datetime import timedelta
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from bookings.models import Booking
from .image_utils import process_item_image, validate_image_file
from .models import Category, Item

User = get_user_model()


class OwnerListingEditTests(TestCase):
    def setUp(self):
        import tempfile
        from django.test import override_settings
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client = APIClient()
        self.owner = User.objects.create_user(email='publisher@example.com', password='p', phone_number='100')
        self.other = User.objects.create_user(email='other@example.com', password='p', phone_number='200')
        self.category = Category.objects.create(name='Cameras')
        self.item = Item.objects.create(owner=self.owner, category=self.category,
            name='Camera', rental_price='0.50', stock=2, description='Original')
        self.url = f'/api/items/mine/{self.item.pk}/'
        self.client.force_authenticate(self.owner)

    def image(self, name):
        buffer = io.BytesIO()
        Image.new('RGB', (32, 32), color='blue').save(buffer, format='JPEG')
        return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')

    def test_owner_retrieves_detail_and_owner_scoped_list(self):
        Item.objects.create(owner=self.other, category=self.category, name='Other', rental_price=5)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.item.pk)
        self.assertEqual(response.data['category_id'], self.category.pk)
        self.assertEqual([row['id'] for row in self.client.get('/api/items/mine/').data['results']], [self.item.pk])

    def test_full_multipart_form_updates_and_retains_images(self):
        from .models import ItemImage
        image = ItemImage.objects.create(item=self.item, image=self.image('original.jpg'), is_primary=True)
        response = self.client.patch(self.url, {
            'name': 'Updated camera', 'description': 'Updated description',
            'category_id': str(self.category.pk), 'rental_price': '0.75', 'stock': '3',
            'deposit': '10.00', 'is_published': 'false', 'rental_kit': '["Charger"]',
            'primary_image_id': str(image.pk),
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        detail = self.client.get(self.url).data
        self.assertEqual(detail['name'], 'Updated camera')
        self.assertEqual(detail['description'], 'Updated description')
        self.assertEqual(detail['rental_price'], '0.75')
        self.assertEqual(detail['stock'], 3)
        self.assertEqual(detail['deposit'], '10.00')
        self.assertFalse(detail['is_published'])
        self.assertEqual(detail['rental_kit'], ['Charger'])
        self.assertEqual(detail['images'][0]['id'], image.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.owner_id, self.owner.pk)

    def test_unchanged_inactive_category_does_not_block_edit(self):
        for deleted in (False, True):
            with self.subTest(deleted=deleted):
                self.category.is_active = False
                self.category.is_deleted = deleted
                self.category.save()
                response = self.client.patch(self.url, {'category_id': self.category.pk,
                    'description': 'Still editable'}, format='multipart')
                self.assertEqual(response.status_code, 200, response.data)
        other_category = Category.objects.create(name='Inactive', is_active=False)
        response = self.client.patch(self.url, {'category_id': other_category.pk}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_other_user_and_guest_cannot_retrieve_or_update(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.patch(self.url, {'name': 'Stolen'}, format='json').status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.patch(self.url, {'stock': 99}, format='json').status_code, 401)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, 'Camera')
        self.assertEqual(self.item.stock, 2)

    def test_replace_image_and_choose_new_cover(self):
        from .models import ItemImage
        old = ItemImage.objects.create(item=self.item, image=self.image('old.jpg'), is_primary=True)
        response = self.client.patch(self.url, {
            'images': [self.image('first.jpg'), self.image('chosen.jpg')],
            'delete_image_ids': f'[{old.pk}]', 'primary_image_index': '1',
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(ItemImage.objects.filter(pk=old.pk).exists())
        self.assertEqual(self.item.images.count(), 2)
        self.assertIn('chosen', self.item.images.get(is_primary=True).image.name)
        self.assertIn('chosen', response.data['primary_image_url'])

    def test_add_new_cover_while_retaining_existing_image(self):
        from .models import ItemImage
        old = ItemImage.objects.create(item=self.item, image=self.image('old.jpg'), is_primary=True)
        response = self.client.patch(self.url, {'images': self.image('new.jpg'),
            'primary_image_index': '0'}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(ItemImage.objects.filter(pk=old.pk).exists())
        self.assertIn('new', self.item.images.get(is_primary=True).image.name)

    def test_rental_kit_150_characters_and_multiple_entries_accepted(self):
        response = self.client.patch(self.url, {
            'rental_kit': '["' + 'A' * 150 + '", "Charger", "Carry case"]',
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['rental_kit'], ['A' * 150, 'Charger', 'Carry case'])
        self.assertEqual(self.client.get(self.url).data['rental_kit'], response.data['rental_kit'])

    def test_rental_kit_151_characters_rejected_before_any_changes(self):
        from .models import RentalKitItem, ItemImage
        original = RentalKitItem.objects.create(item=self.item, name='Original charger')
        image = ItemImage.objects.create(item=self.item, image=self.image('original.jpg'), is_primary=True)
        original_updated_at = self.item.updated_at
        for request_format, entries in (
            ('json', ['Valid charger', 'X' * 151]),
            ('json', [{'name': 'Valid charger'}, {'name': 'X' * 151}]),
            ('multipart', '["Valid charger", "' + 'X' * 151 + '"]'),
            ('multipart', 'Valid charger,' + 'X' * 151),
        ):
            with self.subTest(request_format=request_format, entries_type=type(entries).__name__):
                response = self.client.patch(self.url, {
                    'name': 'Must not save', 'description': 'Must not save',
                    'stock': 99, 'rental_price': '99.00', 'rental_kit': entries,
                    'delete_image_ids': f'[{image.pk}]',
                }, format=request_format)
                self.assertEqual(response.status_code, 400, response.data)
                message = str(response.data['rental_kit']['1'][0])
                self.assertIn('Entry 2', message)
                self.assertIn('150', message)
                self.assertIn('151', message)
                self.item.refresh_from_db()
                self.assertEqual(self.item.name, 'Camera')
                self.assertEqual(self.item.description, 'Original')
                self.assertEqual(self.item.stock, 2)
                self.assertEqual(str(self.item.rental_price), '0.50')
                self.assertEqual(self.item.updated_at, original_updated_at)
                self.assertEqual(list(self.item.rental_kit_items.values_list('id', 'name')),
                                 [(original.pk, 'Original charger')])
                self.assertTrue(ItemImage.objects.filter(pk=image.pk).exists())

    def test_valid_rental_kit_formats_replace_entries_and_omission_retains_them(self):
        from .models import RentalKitItem
        RentalKitItem.objects.create(item=self.item, name='Old kit')
        for request_format, entries in (
            ('json', ['Charger', 'Carry case']),
            ('json', [{'name': 'Charger'}, {'name': 'Carry case'}]),
            ('multipart', '["Charger", "Carry case"]'),
            ('multipart', '[{"name": "Charger"}, {"name": "Carry case"}]'),
            ('multipart', 'Charger,Carry case'),
        ):
            with self.subTest(request_format=request_format, entries_type=type(entries).__name__):
                response = self.client.patch(self.url, {'rental_kit': entries}, format=request_format)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['rental_kit'], ['Charger', 'Carry case'])
        self.assertEqual(self.client.patch(self.url, {'description': 'Only description'}, format='json').status_code, 200)
        self.assertEqual(list(self.item.rental_kit_items.values_list('name', flat=True)), ['Charger', 'Carry case'])

    def test_other_user_cannot_update_rental_kit(self):
        from .models import RentalKitItem
        original = RentalKitItem.objects.create(item=self.item, name='Original charger')
        self.client.force_authenticate(self.other)
        response = self.client.patch(self.url, {'rental_kit': ['Replacement']}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(list(self.item.rental_kit_items.values_list('id', 'name')),
                         [(original.pk, 'Original charger')])

    def test_create_and_admin_update_also_validate_rental_kit(self):
        for url in ('/api/items/', '/api/admin/items/'):
            self.owner.is_staff = url.startswith('/api/admin/')
            self.owner.save(update_fields=['is_staff'])
            response = self.client.post(url, {'name': 'Invalid new item',
                'category_id': self.category.pk, 'rental_price': '5.00',
                'rental_kit': ['X' * 151]}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn('0', response.data['rental_kit'])
            self.assertEqual(Item.objects.count(), 1)
        response = self.client.patch(f'/api/admin/items/{self.item.pk}/', {
            'name': 'Must not save', 'rental_kit': ['X' * 151]}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, 'Camera')


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


class ItemBookingStatusTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email="owner@rentbee.com",
            password="p",
            full_name="Alice Owner",
            phone_number="9876543210"
        )
        self.renter = User.objects.create_user(
            email="renter@secret.com",
            password="p",
            full_name="Bob Renter",
            phone_number="1234567890"
        )
        self.other_user = User.objects.create_user(
            email="other@rentbee.com",
            password="p",
            full_name="Charlie Other",
            phone_number="5555555555"
        )
        self.category = Category.objects.create(name="Electronics", icon="💻", is_active=True)
        self.item = Item.objects.create(
            name="DSLR Pro Camera",
            category=self.category,
            owner=self.owner,
            rental_price=500.00,
            stock=1,
            is_published=True
        )

    def test_future_confirmed_booking_leaves_stock_available_today(self):
        today = timezone.localdate()
        Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=5),
            duration_days=4,
            daily_price=500.00,
            rental_amount=2000.00,
            deposit_amount=1000.00,
            total_amount=3000.00,
            status='waiting_for_pickup',
            payment_status='paid'
        )
        res = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_currently_booked"])
        self.assertTrue(res.data["is_available"])
        self.assertIsNotNone(res.data["current_booking"])
        self.assertEqual(res.data["current_booking"]["start_date"], str(today + timedelta(days=1)))
        self.assertEqual(res.data["current_booking"]["end_date"], str(today + timedelta(days=5)))
        self.assertEqual(res.data["current_booking"]["next_available_date"], str(today))
        self.assertEqual(res.data["current_booking"]["status"], "waiting_for_pickup")

    def test_item_with_confirmed_rental_in_progress_is_booked(self):
        today = timezone.localdate()
        Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=3),
            duration_days=5,
            daily_price=500.00,
            rental_amount=2500.00,
            deposit_amount=1000.00,
            total_amount=3500.00,
            status='rental_in_progress',
            payment_status='paid'
        )
        res = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_currently_booked"])
        self.assertFalse(res.data["is_available"])
        self.assertIsNotNone(res.data["current_booking"])
        self.assertEqual(res.data["current_booking"]["status"], "rental_in_progress")

    def test_item_with_pending_approval_is_available(self):
        today = timezone.localdate()
        Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            daily_price=500.00,
            rental_amount=1000.00,
            deposit_amount=0,
            total_amount=1000.00,
            status='pending_approval'
        )
        res = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_currently_booked"])
        self.assertTrue(res.data["is_available"])
        self.assertIsNone(res.data["current_booking"])

    def test_item_with_past_expired_booking_is_available(self):
        today = timezone.localdate()
        Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=2),
            duration_days=8,
            daily_price=500.00,
            rental_amount=4000.00,
            deposit_amount=0,
            total_amount=4000.00,
            status='waiting_for_pickup'  # end date is in the past
        )
        res = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_currently_booked"])
        self.assertTrue(res.data["is_available"])
        self.assertIsNone(res.data["current_booking"])

    def test_item_with_cancelled_or_rejected_booking_is_available(self):
        today = timezone.localdate()
        Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=4),
            duration_days=3,
            daily_price=500.00,
            rental_amount=1500.00,
            deposit_amount=0,
            total_amount=1500.00,
            status='cancelled'
        )
        Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today + timedelta(days=5),
            end_date=today + timedelta(days=8),
            duration_days=3,
            daily_price=500.00,
            rental_amount=1500.00,
            deposit_amount=0,
            total_amount=1500.00,
            status='rejected'
        )
        res = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_currently_booked"])
        self.assertTrue(res.data["is_available"])
        self.assertIsNone(res.data["current_booking"])

    def test_renter_personal_info_not_leaked_in_current_booking(self):
        today = timezone.localdate()
        Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today,
            end_date=today + timedelta(days=3),
            duration_days=3,
            daily_price=500.00,
            rental_amount=1500.00,
            deposit_amount=0,
            total_amount=1500.00,
            status='waiting_for_pickup'
        )
        res = self.client.get(f"/api/items/{self.item.id}/")
        booking_data = res.data.get("current_booking")
        self.assertIsNotNone(booking_data)
        # Verify allowed keys only
        self.assertEqual(set(booking_data.keys()), {'start_date', 'end_date', 'next_available_date', 'status'})
        # Verify no personal details leaked
        self.assertNotIn("renter", booking_data)
        self.assertNotIn("renter_id", booking_data)
        self.assertNotIn("Bob", str(booking_data))
        self.assertNotIn("secret.com", str(booking_data))
        self.assertNotIn("1234567890", str(booking_data))

    def test_current_user_booking_distinguished_from_other_user_booking(self):
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=4),
            duration_days=3,
            daily_price=500.00,
            rental_amount=1500.00,
            deposit_amount=0,
            total_amount=1500.00,
            status='waiting_for_pickup',
            payment_status='paid'
        )

        # 1. When authenticated as the booking renter (Bob Renter):
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_booked_by_current_user"])
        self.assertFalse(res.data["is_currently_booked"])
        self.assertTrue(res.data["is_available"])
        self.assertIsNotNone(res.data["user_booking"])
        self.assertEqual(res.data["user_booking"]["id"], booking.id)
        self.assertEqual(res.data["user_booking"]["start_date"], str(today + timedelta(days=1)))
        self.assertEqual(res.data["user_booking"]["end_date"], str(today + timedelta(days=4)))
        self.assertEqual(res.data["user_booking"]["status"], "waiting_for_pickup")

        # 2. When authenticated as another user (Charlie Other):
        self.client.force_authenticate(user=self.other_user)
        res_other = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)
        self.assertFalse(res_other.data["is_booked_by_current_user"])
        self.assertIsNone(res_other.data["user_booking"])
        self.assertFalse(res_other.data["is_currently_booked"])
        self.assertTrue(res_other.data["is_available"])
        self.assertIsNotNone(res_other.data["current_booking"])
        self.assertEqual(res_other.data["current_booking"]["start_date"], str(today + timedelta(days=1)))
        self.assertEqual(res_other.data["current_booking"]["end_date"], str(today + timedelta(days=4)))
        # Strictly no personal details
        self.assertNotIn("Bob", str(res_other.data["current_booking"]))
        self.assertNotIn("secret.com", str(res_other.data["current_booking"]))

        # 3. When unauthenticated (Guest):
        self.client.force_authenticate(user=None)
        res_guest = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res_guest.status_code, status.HTTP_200_OK)
        self.assertFalse(res_guest.data["is_booked_by_current_user"])
        self.assertIsNone(res_guest.data["user_booking"])
        self.assertFalse(res_guest.data["is_currently_booked"])
        self.assertTrue(res_guest.data["is_available"])
        self.assertIsNotNone(res_guest.data["current_booking"])

    def test_multiple_bookings_independent_handling(self):
        today = timezone.localdate()
        # Booking 1: Renter (Nov 10-12)
        booking1 = Booking.objects.create(
            renter=self.renter,
            owner=self.owner,
            item=self.item,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            daily_price=500.00,
            rental_amount=1000.00,
            deposit_amount=0,
            total_amount=1000.00,
            status='waiting_for_pickup',
            payment_status='paid'
        )
        # Booking 2: Other user (Nov 15-20)
        booking2 = Booking.objects.create(
            renter=self.other_user,
            owner=self.owner,
            item=self.item,
            start_date=today + timedelta(days=6),
            end_date=today + timedelta(days=11),
            duration_days=5,
            daily_price=500.00,
            rental_amount=2500.00,
            deposit_amount=0,
            total_amount=2500.00,
            status='waiting_for_pickup',
            payment_status='paid'
        )

        # For Bob Renter, his own booking dates are selected for user_booking
        self.client.force_authenticate(user=self.renter)
        res_renter = self.client.get(f"/api/items/{self.item.id}/")
        self.assertTrue(res_renter.data["is_booked_by_current_user"])
        self.assertEqual(res_renter.data["user_booking"]["id"], booking1.id)
        self.assertEqual(res_renter.data["user_booking"]["start_date"], str(today + timedelta(days=1)))
        self.assertEqual(res_renter.data["user_booking"]["end_date"], str(today + timedelta(days=3)))

        # For Charlie Other, his own booking dates are selected for user_booking
        self.client.force_authenticate(user=self.other_user)
        res_other = self.client.get(f"/api/items/{self.item.id}/")
        self.assertTrue(res_other.data["is_booked_by_current_user"])
        self.assertEqual(res_other.data["user_booking"]["id"], booking2.id)
        self.assertEqual(res_other.data["user_booking"]["start_date"], str(today + timedelta(days=6)))
        self.assertEqual(res_other.data["user_booking"]["end_date"], str(today + timedelta(days=11)))

    def test_inactive_and_pending_bookings_do_not_mark_item_as_booked(self):
        today = timezone.localdate()
        for s in ['pending_approval', 'completed', 'cancelled', 'rejected', 'expired']:
            Booking.objects.create(
                renter=self.renter,
                owner=self.owner,
                item=self.item,
                start_date=today + timedelta(days=1),
                end_date=today + timedelta(days=3),
                duration_days=2,
                daily_price=500.00,
                rental_amount=1000.00,
                deposit_amount=0,
                total_amount=1000.00,
                status=s,
                payment_status='pending'
            )

        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f"/api/items/{self.item.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_booked_by_current_user"])
        self.assertFalse(res.data["is_currently_booked"])
        self.assertTrue(res.data["is_available"])
        self.assertIsNone(res.data["user_booking"])
        self.assertIsNone(res.data["current_booking"])


class UserItemCreationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="lender@rentbee.com",
            password="password123",
            full_name="Sarah Lender",
            phone_number="9876543210",
            is_staff=False
        )
        self.category = Category.objects.create(name="Electronics", icon="📷", is_active=True)

    def test_unauthenticated_user_cannot_create_item(self):
        res = self.client.post("/api/items/", {
            "name": "Sony Camera",
            "category_id": self.category.id,
            "rental_price": "500.00",
            "stock": 1
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_create_item_with_ownership_assigned(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post("/api/items/", {
            "name": "Sony Alpha A7 IV",
            "category_id": self.category.id,
            "rental_price": "650.00",
            "deposit": "1000.00",
            "stock": 2,
            "description": "Professional mirrorless full-frame camera.",
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "Sony Alpha A7 IV")
        self.assertEqual(res.data["owner"], self.user.id)
        self.assertEqual(res.data["owner_name"], "Sarah Lender")
        self.assertTrue(res.data["is_published"])
        self.assertFalse(res.data["is_deleted"])

        item = Item.objects.get(id=res.data["id"])
        self.assertEqual(item.owner, self.user)
        self.assertEqual(item.rental_price, 650.00)
        self.assertEqual(item.deposit, 1000.00)
        self.assertEqual(item.stock, 2)

    def test_user_can_upload_images_and_set_primary_cover(self):
        self.client.force_authenticate(user=self.user)

        img1 = Image.new('RGB', (100, 100), color='red')
        buf1 = io.BytesIO()
        img1.save(buf1, format='JPEG')
        file1 = SimpleUploadedFile("cover.jpg", buf1.getvalue(), content_type="image/jpeg")

        img2 = Image.new('RGB', (100, 100), color='green')
        buf2 = io.BytesIO()
        img2.save(buf2, format='JPEG')
        file2 = SimpleUploadedFile("side.jpg", buf2.getvalue(), content_type="image/jpeg")

        res = self.client.post("/api/items/", {
            "name": "Tripod Professional",
            "category_id": self.category.id,
            "rental_price": "150.00",
            "stock": 1,
            "images": [file1, file2],
            "primary_image_index": 1,
        }, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        item = Item.objects.get(id=res.data["id"])
        self.assertEqual(item.images.count(), 2)

        primary_img = item.images.filter(is_primary=True).first()
        self.assertIsNotNone(primary_img)
        self.assertTrue(primary_img.is_primary)
        self.assertEqual(item.images.first(), primary_img)
        self.assertIn("side", primary_img.image.name)

    def test_user_item_creates_rental_kit(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post("/api/items/", {
            "name": "Drone 4K",
            "category_id": self.category.id,
            "rental_price": "1200.00",
            "stock": 1,
            "rental_kit": '["Extra Battery", "Controller", "Carrying Case"]'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        item = Item.objects.get(id=res.data["id"])
        kit_items = list(item.rental_kit_items.values_list('name', flat=True))
        self.assertEqual(kit_items, ["Extra Battery", "Controller", "Carrying Case"])

    def test_created_item_is_immediately_visible_in_public_browse(self):
        self.client.force_authenticate(user=self.user)
        create_res = self.client.post("/api/items/", {
            "name": "GoPro Hero 11",
            "category_id": self.category.id,
            "rental_price": "350.00",
            "stock": 1,
        })
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        item_id = create_res.data["id"]

        # Public unauthenticated user browses items
        anon_client = APIClient()
        browse_res = anon_client.get("/api/items/")
        self.assertEqual(browse_res.status_code, status.HTTP_200_OK)
        ids = [it["id"] for it in browse_res.data["results"]]
        self.assertIn(item_id, ids)

    def test_item_detail_serializes_is_owner(self):
        from decimal import Decimal
        item = Item.objects.create(
            name="Professional Tripod",
            owner=self.user,
            category=self.category,
            rental_price=Decimal("150.00"),
            stock=1
        )
        # 1. Item Owner views own item -> is_owner is True
        self.client.force_authenticate(user=self.user)
        res_owner = self.client.get(f"/api/items/{item.id}/")
        self.assertEqual(res_owner.status_code, status.HTTP_200_OK)
        self.assertTrue(res_owner.data.get("is_owner"))

        # 2. Other authenticated user views item -> is_owner is False
        other_user = get_user_model().objects.create_user(email="other_renter@test.com", password="Password123!")
        self.client.force_authenticate(user=other_user)
        res_other = self.client.get(f"/api/items/{item.id}/")
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)
        self.assertFalse(res_other.data.get("is_owner"))

        # 3. Unauthenticated guest views item -> is_owner is False
        anon_client = APIClient()
        res_anon = anon_client.get(f"/api/items/{item.id}/")
        self.assertEqual(res_anon.status_code, status.HTTP_200_OK)
        self.assertFalse(res_anon.data.get("is_owner"))








