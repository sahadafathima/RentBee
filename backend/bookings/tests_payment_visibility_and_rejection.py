import hashlib
import hmac
from decimal import Decimal
from datetime import timedelta
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from addresses.models import Address
from catalog.models import Category, Item
from bookings.models import Booking, InAppNotification

User = get_user_model()


@override_settings(RAZORPAY_KEY_ID='rzp_test_key', RAZORPAY_KEY_SECRET='rzp_test_secret')
class BookingPaymentVisibilityAndRejectionTests(TestCase):
    def setUp(self):
        self.client = APIClient()   #APIClient is used to test whether backend APIs work correctly without involving the frontend#

        # Users
        self.owner = User.objects.create_user(
            email='alice.owner@test.com',
            password='Password123!',
            full_name='Alice Owner',
            phone_number='9876543210'
        )
        self.renter = User.objects.create_user(
            email='bob.renter@test.com',
            password='Password123!',
            full_name='Bob Renter',
            phone_number='9876543211'
        )
        self.stranger = User.objects.create_user(
            email='charlie.stranger@test.com',
            password='Password123!',
            full_name='Charlie Stranger',
            phone_number='9876543212'
        )
        self.staff_admin = User.objects.create_superuser(
            email='admin@test.com',
            password='Password123!',
            full_name='Admin User',
            phone_number='9876543213'
        )

        # Addresses
        self.owner_address = Address.objects.create(
            user=self.owner,
            full_name='Alice Owner',
            house_number='House 42B',
            address='Rosewood Lane',
            area='Greenwood Heights',
            landmark='Opposite Central Park',
            city='Bangalore',
            state='Karnataka',
            pincode='560001',
            country='India',
            address_type='Home'
        )
        self.renter_address = Address.objects.create(
            user=self.renter,
            full_name='Bob Renter',
            house_number='Flat 101',
            address='Lake View Road',
            area='Indiranagar',
            landmark='Near Metro',
            city='Bangalore',
            state='Karnataka',
            pincode='560038',
            country='India',
            address_type='Home'
        )

        # Category & Item
        self.category = Category.objects.create(name='Cameras', icon='📷', is_active=True)
        self.item = Item.objects.create(
            name='Sony A7 IV Camera',
            category=self.category,
            owner=self.owner,
            rental_price=Decimal('1000.00'),
            deposit=Decimal('2000.00'),
            stock=5,
            is_published=True
        )

    def _create_booking(self, status='pending_approval', payment_method='online', payment_status='pending'):
        start_date = timezone.localdate() + timedelta(days=2)
        end_date = start_date + timedelta(days=3)
        return Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=start_date,
            end_date=end_date,
            duration_days=3,
            requested_quantity=1,
            daily_price=Decimal('1000.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('2000.00'),
            total_amount=Decimal('5000.00'),
            status=status,
            payment_method=payment_method,
            payment_status=payment_status,
            renter_address=self.renter_address,
        )

    # ==================== PAYMENT TESTS ====================

    def test_01_pending_booking_pay_now_hidden(self):
        """1. Pending booking: Pay Now is hidden (can_pay is False)."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['can_pay'])

    def test_02_accepted_booking_pay_now_appears_when_payment_required(self):
        """2. Accepted booking: Pay Now appears when payment is required (can_pay is True)."""
        booking = self._create_booking(status='waiting_for_pickup', payment_status='pending')
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['can_pay'])

    def test_03_rejected_booking_pay_now_hidden(self):
        """3. Rejected booking: Pay Now is hidden (can_pay is False)."""
        booking = self._create_booking(status='rejected', payment_status='pending')
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['can_pay'])

    def test_04_cancelled_and_expired_bookings_pay_now_hidden(self):
        """4. Cancelled and expired bookings: Pay Now is hidden (can_pay is False)."""
        cancelled_booking = self._create_booking(status='cancelled', payment_status='pending')
        expired_booking = self._create_booking(status='expired', payment_status='pending')
        self.client.force_authenticate(user=self.renter)

        res_cancelled = self.client.get(f'/api/bookings/{cancelled_booking.id}/')
        self.assertFalse(res_cancelled.data['can_pay'])

        res_expired = self.client.get(f'/api/bookings/{expired_booking.id}/')
        self.assertFalse(res_expired.data['can_pay'])

    def test_05_direct_razorpay_api_attempt_for_pending_booking_is_rejected(self):
        """5. Direct Razorpay API attempt for a pending booking is rejected by the backend."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('after the owner accepts', res.data.get('error', ''))

    def test_06_direct_offline_payment_attempt_for_pending_booking_is_rejected(self):
        """6. Direct offline payment attempt for a pending booking is rejected by the backend."""
        booking = self._create_booking(status='pending_approval', payment_method='offline')
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('waiting for pickup', res.data.get('error', ''))

    @patch('bookings.services.get_razorpay_client')
    def test_07_accepted_bookings_can_create_payment_order(self, mock_client):
        """7. Accepted bookings can still use existing payment methods (Razorpay order created)."""
        mock_instance = MagicMock()
        mock_instance.order.create.return_value = {
            'id': 'order_test_123',
            'amount': 500000,
            'currency': 'INR',
            'status': 'created'
        }
        mock_client.return_value = mock_instance

        booking = self._create_booking(status='waiting_for_pickup')
        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['order_id'], 'order_test_123')

    @patch('bookings.services.get_razorpay_client')
    def test_08_existing_payment_verification_still_works(self, mock_client):
        """8. Existing payment verification still works for accepted booking."""
        booking = self._create_booking(status='waiting_for_pickup')
        booking.razorpay_order_id = 'order_test_123'
        booking.save()

        # Compute valid HMAC signature
        key_secret = 'rzp_test_secret'
        msg = f"{booking.razorpay_order_id}|pay_test_456".encode('utf-8')
        sig = hmac.new(key_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        mock_instance = MagicMock()
        mock_instance.payment.fetch.return_value = {
            'id': 'pay_test_456',
            'order_id': 'order_test_123',
            'status': 'captured',
            'amount': int(booking.total_amount * 100),
            'currency': 'INR'
        }
        mock_client.return_value = mock_instance

        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', {
            'razorpay_order_id': booking.razorpay_order_id,
            'razorpay_payment_id': 'pay_test_456',
            'razorpay_signature': sig
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_transaction_id, 'pay_test_456')

    # ==================== REJECTION TESTS ====================

    def test_09_owner_cannot_reject_without_a_reason(self):
        """9. Owner cannot reject without a reason."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)

        # Empty payload
        res_empty = self.client.post(f'/api/bookings/{booking.id}/reject/', {}, format='json')
        self.assertEqual(res_empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rejection reason is required', res_empty.data.get('error', ''))

        # Blank string
        res_blank = self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': ''}, format='json')
        self.assertEqual(res_blank.status_code, status.HTTP_400_BAD_REQUEST)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending_approval')

    def test_10_whitespace_only_rejection_reason_is_rejected(self):
        """10. Whitespace-only rejection reason is rejected."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': '   \t  \n  '}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rejection reason is required', res.data.get('error', ''))

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending_approval')

    def test_11_valid_rejection_reason_is_saved_correctly(self):
        """11. Valid rejection reason is saved correctly."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)

        reason = 'Item is undergoing routine calibration on those dates.'
        res = self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': reason}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rejected')
        self.assertEqual(booking.rejection_reason, reason)
        self.assertIsNotNone(booking.rejected_at)
        self.assertEqual(booking.cancelled_by, self.owner)

    def test_12_only_correct_owner_or_authorized_admin_can_reject(self):
        """12. Only the correct owner or authorized admin can reject."""
        booking = self._create_booking(status='pending_approval')

        # Stranger attempts rejection -> 403 Forbidden
        self.client.force_authenticate(user=self.stranger)
        res_stranger = self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': 'Not my item'}, format='json')
        self.assertEqual(res_stranger.status_code, status.HTTP_403_FORBIDDEN)

        # Renter attempts rejection -> 403 Forbidden
        self.client.force_authenticate(user=self.renter)
        res_renter = self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': 'Renter cannot reject'}, format='json')
        self.assertEqual(res_renter.status_code, status.HTTP_403_FORBIDDEN)

        # Staff admin attempts rejection -> 200 OK
        self.client.force_authenticate(user=self.staff_admin)
        res_admin = self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': 'Admin intervened'}, format='json')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rejected')

    def test_13_customer_receives_in_app_rejection_notification(self):
        """13. Customer receives an in-app rejection notification."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)

        reason = 'Equipment unavailable for requested duration.'
        self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': reason}, format='json')

        notifs = InAppNotification.objects.filter(user=self.renter, booking=booking, event='rejected')
        self.assertEqual(notifs.count(), 1)
        notif = notifs.first()
        self.assertEqual(notif.title, 'Booking Request Rejected')
        self.assertIn(booking.item.name, notif.message)
        self.assertIn(booking.booking_reference, notif.message)
        self.assertIn(reason, notif.message)

    def test_14_notification_opens_correct_booking_details_page(self):
        """14. Notification contains reference to the correct booking ID."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)
        self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': 'Not available'}, format='json')

        self.client.force_authenticate(user=self.renter)
        res = self.client.get('/api/bookings/notifications/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get('results', [])
        rejected_notif = next((n for n in results if n.get('event') == 'rejected'), None)
        self.assertIsNotNone(rejected_notif)
        self.assertEqual(rejected_notif['booking'], booking.id)

    def test_15_customer_can_see_exact_rejection_reason(self):
        """15. Customer can see the exact rejection reason on Booking Details page."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)
        reason = 'Unavailable due to scheduled studio shoot.'
        self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': reason}, format='json')

        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'rejected')
        self.assertEqual(res.data['rejection_reason'], reason)

    def test_16_unrelated_users_cannot_access_rejection_reason(self):
        """16. Unrelated users cannot access the rejection reason (403 Forbidden)."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)
        self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': 'Private reason'}, format='json')

        # Third party user accesses booking details -> 403 Forbidden
        self.client.force_authenticate(user=self.stranger)
        res = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_17_rejected_bookings_cannot_proceed_to_payment(self):
        """17. Rejected bookings cannot proceed to payment (both order creation and verification fail)."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)
        self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': 'Item unavailable'}, format='json')

        self.client.force_authenticate(user=self.renter)
        # 1. Order creation attempt
        res_order = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res_order.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Payment cannot be initiated', res_order.data.get('error', ''))

        # 2. Verification attempt
        res_verify = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', {
            'razorpay_order_id': 'fake_order',
            'razorpay_payment_id': 'fake_pay',
            'razorpay_signature': 'fake_sig'
        }, format='json')
        self.assertEqual(res_verify.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================== REGRESSION TESTS ====================

    def test_18_existing_booking_approval_workflow_still_works(self):
        """18. Existing booking approval workflow still works."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(f'/api/bookings/{booking.id}/approve/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'waiting_for_pickup')
        self.assertIsNotNone(booking.approved_at)

    def test_19_existing_10_percent_first_booking_offer_remains_unchanged(self):
        """19. Existing 10% first-booking offer remains unchanged."""
        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=5)
        end = start + timedelta(days=2)  # 2 days

        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
            'requested_quantity': 1,
            'payment_method': 'online',
            'address_id': self.renter_address.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Daily: 1000, 2 days = 2000 rental. 10% discount = 200. Net rental: 1800. Deposit: 2000. Total: 3800.
        self.assertEqual(Decimal(str(res.data['original_rental_amount'])), Decimal('2000.00'))
        self.assertEqual(Decimal(str(res.data['discount_amount'])), Decimal('200.00'))
        self.assertEqual(Decimal(str(res.data['rental_amount'])), Decimal('1800.00'))
        self.assertEqual(Decimal(str(res.data['total_amount'])), Decimal('3800.00'))

    def test_20_existing_offline_payment_confirmation_works_for_accepted_booking(self):
        """20. Existing Offline Pay at Pickup functionality remains intact."""
        booking = self._create_booking(status='waiting_for_pickup', payment_method='offline')
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_verified_by, self.owner)
        self.assertIsNotNone(booking.payment_verified_at)

    def test_21_existing_invoice_remains_intact_for_paid_booking(self):
        """21. Existing invoice and receipt functionality remains intact."""
        booking = self._create_booking(status='waiting_for_pickup', payment_status='paid')
        self.client.force_authenticate(user=self.renter)

        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', res['Content-Disposition'])

