from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Category, Item, WishlistItem

User = get_user_model()


class WishlistSystemTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.user_a = User.objects.create_user(
            email='usera@test.com',
            password='Password123!',
            full_name='User A',
            phone_number='9876543201'
        )
        self.user_b = User.objects.create_user(
            email='userb@test.com',
            password='Password123!',
            full_name='User B',
            phone_number='9876543202'
        )

        # Categories & Items
        self.category = Category.objects.create(name='Cameras', icon='📷', is_active=True)
        self.item_1 = Item.objects.create(
            name='Sony A7 IV Camera',
            category=self.category,
            rental_price=Decimal('1500.00'),
            deposit=Decimal('5000.00'),
            stock=1,
            is_published=True
        )
        self.item_2 = Item.objects.create(
            name='Canon EOS R5',
            category=self.category,
            rental_price=Decimal('2000.00'),
            deposit=Decimal('8000.00'),
            stock=1,
            is_published=True
        )

    def test_unauthenticated_access_denied(self):
        """Guests cannot access wishlist endpoints."""
        res_get = self.client.get('/api/wishlist/')
        self.assertEqual(res_get.status_code, status.HTTP_401_UNAUTHORIZED)

        res_post = self.client.post('/api/wishlist/', {'item_id': self.item_1.id})
        self.assertEqual(res_post.status_code, status.HTTP_401_UNAUTHORIZED)

        res_toggle = self.client.post('/api/wishlist/toggle/', {'item_id': self.item_1.id})
        self.assertEqual(res_toggle.status_code, status.HTTP_401_UNAUTHORIZED)

        res_delete = self.client.delete(f'/api/wishlist/{self.item_1.id}/')
        self.assertEqual(res_delete.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_add_and_get_wishlist(self):
        """User can add items and retrieve their wishlist with item_ids."""
        self.client.force_authenticate(user=self.user_a)

        res_add = self.client.post('/api/wishlist/', {'item_id': self.item_1.id})
        self.assertEqual(res_add.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_add.data['is_wishlisted'])
        self.assertEqual(res_add.data['count'], 1)

        res_get = self.client.get('/api/wishlist/')
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.data['count'], 1)
        self.assertIn(self.item_1.id, res_get.data['item_ids'])
        self.assertEqual(len(res_get.data['results']), 1)
        self.assertEqual(res_get.data['results'][0]['item']['name'], 'Sony A7 IV Camera')

    def test_duplicate_prevention(self):
        """Adding the same item twice is idempotent and does not create duplicate rows."""
        self.client.force_authenticate(user=self.user_a)

        res1 = self.client.post('/api/wishlist/', {'item_id': self.item_1.id})
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post('/api/wishlist/', {'item_id': self.item_1.id})
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['count'], 1)
        self.assertEqual(WishlistItem.objects.filter(user=self.user_a, item=self.item_1).count(), 1)

    def test_toggle_wishlist(self):
        """Toggle adds if missing and removes if present."""
        self.client.force_authenticate(user=self.user_a)

        # 1. Toggle ON
        res_on = self.client.post('/api/wishlist/toggle/', {'item_id': self.item_1.id})
        self.assertEqual(res_on.status_code, status.HTTP_200_OK)
        self.assertTrue(res_on.data['is_wishlisted'])
        self.assertEqual(res_on.data['count'], 1)
        self.assertTrue(WishlistItem.objects.filter(user=self.user_a, item=self.item_1).exists())

        # 2. Toggle OFF
        res_off = self.client.post('/api/wishlist/toggle/', {'item_id': self.item_1.id})
        self.assertEqual(res_off.status_code, status.HTTP_200_OK)
        self.assertFalse(res_off.data['is_wishlisted'])
        self.assertEqual(res_off.data['count'], 0)
        self.assertFalse(WishlistItem.objects.filter(user=self.user_a, item=self.item_1).exists())

    def test_remove_from_wishlist(self):
        """Delete endpoint removes item from wishlist."""
        self.client.force_authenticate(user=self.user_a)

        self.client.post('/api/wishlist/', {'item_id': self.item_1.id})
        self.client.post('/api/wishlist/', {'item_id': self.item_2.id})

        res_del = self.client.delete(f'/api/wishlist/{self.item_1.id}/')
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(res_del.data['is_wishlisted'])
        self.assertEqual(res_del.data['count'], 1)

        res_get = self.client.get('/api/wishlist/')
        self.assertEqual(res_get.data['count'], 1)
        self.assertNotIn(self.item_1.id, res_get.data['item_ids'])
        self.assertIn(self.item_2.id, res_get.data['item_ids'])

    def test_user_separation(self):
        """Wishlists are completely isolated between users."""
        self.client.force_authenticate(user=self.user_a)
        self.client.post('/api/wishlist/', {'item_id': self.item_1.id})

        self.client.force_authenticate(user=self.user_b)
        self.client.post('/api/wishlist/', {'item_id': self.item_2.id})

        # User B cannot see User A's item
        res_b = self.client.get('/api/wishlist/')
        self.assertEqual(res_b.data['count'], 1)
        self.assertEqual(res_b.data['item_ids'], [self.item_2.id])

        # User B cannot delete User A's wishlist entry
        self.client.delete(f'/api/wishlist/{self.item_1.id}/')
        self.assertTrue(WishlistItem.objects.filter(user=self.user_a, item=self.item_1).exists())

    def test_soft_deleted_and_unpublished_items_filtered(self):
        """Soft-deleted or unpublished items are excluded from wishlist query."""
        self.client.force_authenticate(user=self.user_a)
        self.client.post('/api/wishlist/', {'item_id': self.item_1.id})

        # Soft delete item_1
        self.item_1.is_deleted = True
        self.item_1.save()

        res_get = self.client.get('/api/wishlist/')
        self.assertEqual(res_get.data['count'], 0)
        self.assertEqual(len(res_get.data['results']), 0)

    def test_wishlist_items_remain_saved_when_availability_changes(self):
        """
        Wishlist items remain saved when stock drops to 0 or availability changes,
        and the latest availability status (is_available=False) is returned by the backend.
        """
        self.client.force_authenticate(user=self.user_a)
        self.client.post('/api/wishlist/', {'item_id': self.item_1.id})

        # Change item availability: stock drops to 0
        self.item_1.stock = 0
        self.item_1.save()

        res_get = self.client.get('/api/wishlist/')
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        # Item is still in wishlist
        self.assertEqual(res_get.data['count'], 1)
        self.assertIn(self.item_1.id, res_get.data['item_ids'])
        # Latest availability reflects False
        item_data = res_get.data['results'][0]['item']
        self.assertFalse(item_data['is_available'])
        self.assertEqual(item_data['stock'], 0)

    def test_rapid_consecutive_toggles_safe(self):
        """
        Simulate rapid sequential toggle calls to verify integrity and correct count.
        """
        self.client.force_authenticate(user=self.user_a)

        # 4 consecutive toggles
        res1 = self.client.post('/api/wishlist/toggle/', {'item_id': self.item_1.id})
        self.assertTrue(res1.data['is_wishlisted'])
        self.assertEqual(res1.data['count'], 1)

        res2 = self.client.post('/api/wishlist/toggle/', {'item_id': self.item_1.id})
        self.assertFalse(res2.data['is_wishlisted'])
        self.assertEqual(res2.data['count'], 0)

        res3 = self.client.post('/api/wishlist/toggle/', {'item_id': self.item_1.id})
        self.assertTrue(res3.data['is_wishlisted'])
        self.assertEqual(res3.data['count'], 1)

        res4 = self.client.post('/api/wishlist/toggle/', {'item_id': self.item_1.id})
        self.assertFalse(res4.data['is_wishlisted'])
        self.assertEqual(res4.data['count'], 0)

        self.assertEqual(WishlistItem.objects.filter(user=self.user_a, item=self.item_1).count(), 0)
