import secrets
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Item, Category
from bookings.models import Booking, InAppNotification
from bookings.services import get_item_availability, mark_booking_payment_verified
from bookings.sms_service import (
    SMSConfigurationError,
    SMSSendError,
    mask_phone,
    normalize_to_e164,
)

User = get_user_model()


class PickupOTPVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create distinct users
        self.owner = User.objects.create_user(
            email='host_otp@example.com',
            password='Password123!',
            full_name='Host Hive',
            phone_number='9876543210'
        )
        self.renter = User.objects.create_user(
            email='renter_otp@example.com',
            password='Password123!',
            full_name='Renter Robin',
            phone_number='9123456789'
        )
        self.stranger = User.objects.create_user(
            email='stranger_otp@example.com',
            password='Password123!',
            full_name='Stranger Sam',
            phone_number='9998887776'
        )

        # Create item
        self.category = Category.objects.create(name='Camera & Gear', icon='camera')
        self.item = Item.objects.create(
            owner=self.owner,
            name='Sony FX3 Cinema Camera',
            category=self.category,
            rental_price=2500,
            deposit=5000,
            stock=3,
            is_published=True
        )

        self.start_date = timezone.localdate() + timedelta(days=1)
        self.end_date = self.start_date + timedelta(days=3)

    def create_booking(self, status='waiting_for_pickup', payment_status='paid'):
        booking = Booking.objects.create(
            booking_reference=f"BK-{secrets.token_hex(3).upper()}",
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=self.start_date,
            end_date=self.end_date,
            duration_days=3,
            requested_quantity=1,
            daily_price=2500,
            rental_amount=7500,
            deposit_amount=5000,
            total_amount=12500,
            status=status,
            payment_status=payment_status,
            payment_verified_at=timezone.now() if payment_status == 'paid' else None
        )
        return booking

    # 1. Owner can generate OTP for an eligible paid booking
    @patch('bookings.views.send_pickup_otp_sms')
    def test_owner_can_generate_otp_for_eligible_paid_booking(self, mock_send_sms):
        mock_send_sms.return_value = {
            'success': True,
            'masked_phone': '******6789',
            'provider': 'twilio',
            'message_id': 'SM12345'
        }
        booking = self.create_booking(status='waiting_for_pickup', payment_status='paid')
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('Pickup OTP sent successfully', res.data['message'])
        self.assertEqual(res.data['masked_phone'], '******6789')
        # Crucial security guarantee: raw OTP is NEVER returned in response
        self.assertNotIn('otp', res.data)
        self.assertNotIn('code', res.data)

        booking.refresh_from_db()
        self.assertTrue(bool(booking.pickup_otp_hash))
        self.assertIsNotNone(booking.pickup_otp_expires_at)
        self.assertIsNotNone(booking.pickup_otp_created_at)
        self.assertEqual(booking.pickup_otp_attempts, 0)
        self.assertTrue(mock_send_sms.called)

    # 2. Renter cannot generate OTP
    @patch('bookings.views.send_pickup_otp_sms')
    def test_renter_cannot_generate_otp(self, mock_send_sms):
        booking = self.create_booking()
        self.client.force_authenticate(user=self.renter)

        res = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Only the item owner', res.data['error'])
        self.assertFalse(mock_send_sms.called)

    # 3. Unrelated user cannot generate OTP
    @patch('bookings.views.send_pickup_otp_sms')
    def test_unrelated_user_cannot_generate_otp(self, mock_send_sms):
        booking = self.create_booking()
        self.client.force_authenticate(user=self.stranger)

        res = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(mock_send_sms.called)

    # 4. Unpaid booking cannot generate OTP
    @patch('bookings.views.send_pickup_otp_sms')
    def test_unpaid_booking_cannot_generate_otp(self, mock_send_sms):
        booking = self.create_booking(status='waiting_for_pickup', payment_status='pending')
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('payment is verified', res.data['error'].lower())
        self.assertFalse(mock_send_sms.called)

    # 5. Pending booking cannot generate OTP
    @patch('bookings.views.send_pickup_otp_sms')
    def test_pending_approval_booking_cannot_generate_otp(self, mock_send_sms):
        booking = self.create_booking(status='pending_approval', payment_status='pending')
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('pending owner approval', res.data['error'])
        self.assertFalse(mock_send_sms.called)

    # 6. Cancelled booking cannot generate OTP
    @patch('bookings.views.send_pickup_otp_sms')
    def test_cancelled_booking_cannot_generate_otp(self, mock_send_sms):
        booking = self.create_booking(status='cancelled', payment_status='paid')
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cancelled', res.data['error'])
        self.assertFalse(mock_send_sms.called)

    # 7. Correct OTP confirms pickup
    def test_correct_otp_confirms_pickup(self):
        booking = self.create_booking()
        raw_otp = '482910'
        booking.pickup_otp_hash = make_password(raw_otp)
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.pickup_otp_created_at = timezone.now()
        booking.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('Pickup confirmed successfully', res.data['message'])

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')
        self.assertIsNotNone(booking.pickup_confirmed_at)
        self.assertIsNotNone(booking.picked_up_at)
        self.assertEqual(booking.pickup_confirmed_by, self.owner)
        # OTP is erased/invalidated on successful verification
        self.assertEqual(booking.pickup_otp_hash, '')
        self.assertIsNone(booking.pickup_otp_expires_at)

        # In-app notification created for renter
        notif = InAppNotification.objects.filter(booking=booking, event='pickup_confirmed').first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.user, self.renter)

    # 8. Incorrect OTP does not confirm pickup
    def test_incorrect_otp_does_not_confirm_pickup(self):
        booking = self.create_booking()
        booking.pickup_otp_hash = make_password('112233')
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.pickup_otp_created_at = timezone.now()
        booking.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': '999999'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Incorrect OTP', res.data['error'])
        self.assertEqual(res.data['attempts_remaining'], 4)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'waiting_for_pickup')
        self.assertIsNone(booking.pickup_confirmed_at)
        self.assertEqual(booking.pickup_otp_attempts, 1)

    # 9. Expired OTP is rejected
    def test_expired_otp_is_rejected(self):
        booking = self.create_booking()
        raw_otp = '654321'
        booking.pickup_otp_hash = make_password(raw_otp)
        # Expired 1 minute ago
        booking.pickup_otp_expires_at = timezone.now() - timedelta(minutes=1)
        booking.pickup_otp_created_at = timezone.now() - timedelta(minutes=11)
        booking.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('expired', res.data['error'].lower())

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'waiting_for_pickup')
        self.assertIsNone(booking.pickup_confirmed_at)

    # 10. OTP cannot be reused
    def test_otp_cannot_be_reused(self):
        booking = self.create_booking()
        raw_otp = '789123'
        booking.pickup_otp_hash = make_password(raw_otp)
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.pickup_otp_created_at = timezone.now()
        booking.save()

        self.client.force_authenticate(user=self.owner)
        # First verification succeeds
        res1 = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Reusing the exact same OTP immediately fails
        res2 = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already been confirmed', res2.data['error'])

    # 11. Maximum 5 incorrect attempts are enforced
    def test_max_five_attempts_enforced_and_invalidates_otp(self):
        booking = self.create_booking()
        raw_otp = '555666'
        booking.pickup_otp_hash = make_password(raw_otp)
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.pickup_otp_created_at = timezone.now()
        booking.save()

        self.client.force_authenticate(user=self.owner)

        # Attempts 1 through 4 fail with decremented remaining count
        for attempt in range(1, 5):
            res = self.client.post(
                f'/api/bookings/{booking.id}/verify-pickup-otp/',
                {'otp': '000000'},
                format='json'
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res.data['attempts_remaining'], 5 - attempt)

        # Attempt 5 reaches max attempts and locks/invalidates OTP
        res5 = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': '000000'},
            format='json'
        )
        self.assertEqual(res5.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Maximum attempts reached', res5.data['error'])

        booking.refresh_from_db()
        self.assertEqual(booking.pickup_otp_hash, '')

        # Attempt with original correct OTP now rejected because OTP is cleared
        res_correct = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )
        self.assertEqual(res_correct.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No active pickup OTP', res_correct.data['error'])

    # 12. Resending OTP invalidates previous OTP
    @patch('bookings.views.send_pickup_otp_sms')
    def test_resending_otp_invalidates_previous_otp(self, mock_send_sms):
        mock_send_sms.return_value = {'success': True, 'masked_phone': '******6789'}
        booking = self.create_booking()
        self.client.force_authenticate(user=self.owner)

        # Generate OTP 1
        res1 = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        hash1 = booking.pickup_otp_hash

        # Fast forward past 60s cooldown
        booking.pickup_otp_created_at = timezone.now() - timedelta(seconds=65)
        booking.save()

        # Generate OTP 2 (resend)
        res2 = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        hash2 = booking.pickup_otp_hash

        # New hash was generated, replacing the old one
        self.assertNotEqual(hash1, hash2)

    # 13. Resend cooldown and rate limiting work
    @patch('bookings.views.send_pickup_otp_sms')
    def test_resend_cooldown_enforced(self, mock_send_sms):
        mock_send_sms.return_value = {'success': True, 'masked_phone': '******6789'}
        booking = self.create_booking()
        self.client.force_authenticate(user=self.owner)

        # First request succeeds
        res1 = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Immediate second request blocked by cooldown
        res2 = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res2.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Please wait', res2.data['error'])
        self.assertTrue(res2.data['cooldown_seconds'] > 0)

    # 14. Renter cannot verify OTP through the owner API
    def test_renter_cannot_verify_otp(self):
        booking = self.create_booking()
        booking.pickup_otp_hash = make_password('123456')
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()

        self.client.force_authenticate(user=self.renter)
        res = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': '123456'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Only the item owner', res.data['error'])

    # 15. Non-owner cannot verify OTP
    def test_non_owner_cannot_verify_otp(self):
        booking = self.create_booking()
        booking.pickup_otp_hash = make_password('123456')
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()

        self.client.force_authenticate(user=self.stranger)
        res = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': '123456'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # 16. Already confirmed pickup cannot be confirmed again
    def test_already_confirmed_pickup_cannot_be_confirmed_again(self):
        booking = self.create_booking(status='rental_in_progress')
        booking.pickup_confirmed_at = timezone.now()
        booking.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': '123456'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already been confirmed', res.data['error'])

    # 17. Rental timer starts at pickup confirmation
    def test_rental_timer_starts_from_pickup_confirmation_timestamp(self):
        booking = self.create_booking()
        raw_otp = '777888'
        booking.pickup_otp_hash = make_password(raw_otp)
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()

        # Before pickup: return_deadline is None
        self.assertIsNone(booking.return_deadline)

        self.client.force_authenticate(user=self.owner)
        confirm_time = timezone.now()
        res = self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertIsNotNone(booking.pickup_confirmed_at)
        self.assertIsNotNone(booking.return_deadline)
        # Expected return deadline is pickup_confirmed_at + duration_days
        expected_deadline = booking.pickup_confirmed_at + timedelta(days=booking.duration_days)
        self.assertEqual(booking.return_deadline, expected_deadline)

    # 18. Stock remains reserved after pickup
    def test_stock_remains_reserved_after_pickup(self):
        booking = self.create_booking()
        # Initial stock for item is 3, reserved 1
        initial_avail = get_item_availability(self.item, self.start_date, self.end_date)
        self.assertEqual(initial_avail['available_stock'], 2)

        raw_otp = '333444'
        booking.pickup_otp_hash = make_password(raw_otp)
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()

        self.client.force_authenticate(user=self.owner)
        self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')

        # Stock is still reserved (available 2 out of 3)
        after_pickup_avail = get_item_availability(self.item, self.start_date, self.end_date)
        self.assertEqual(after_pickup_avail['available_stock'], 2)

    # 19. Existing return confirmation still works
    def test_existing_return_confirmation_works_and_releases_stock(self):
        booking = self.create_booking()
        raw_otp = '999111'
        booking.pickup_otp_hash = make_password(raw_otp)
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()

        self.client.force_authenticate(user=self.owner)
        self.client.post(
            f'/api/bookings/{booking.id}/verify-pickup-otp/',
            {'otp': raw_otp},
            format='json'
        )

        # Host confirms return of item
        res_return = self.client.post(f'/api/bookings/{booking.id}/confirm-return/')
        self.assertEqual(res_return.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')
        self.assertIsNotNone(booking.returned_at)

        # Stock is now released back to full 3
        after_return_avail = get_item_availability(self.item, self.start_date, self.end_date)
        self.assertEqual(after_return_avail['available_stock'], 3)

    # 20. Direct confirm-pickup endpoint requires OTP and cannot bypass
    def test_direct_confirm_pickup_endpoint_requires_otp_cannot_bypass(self):
        booking = self.create_booking()
        self.client.force_authenticate(user=self.owner)

        # Attempt to confirm pickup without OTP: strictly blocked
        res_no_otp = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/')
        self.assertEqual(res_no_otp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('requires OTP verification', res_no_otp.data['error'])

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'waiting_for_pickup')
        self.assertIsNone(booking.pickup_confirmed_at)

        # Provide valid OTP to confirm-pickup: succeeds
        raw_otp = '654987'
        booking.pickup_otp_hash = make_password(raw_otp)
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()

        res_with_otp = self.client.post(
            f'/api/bookings/{booking.id}/confirm-pickup/',
            {'otp': raw_otp},
            format='json'
        )
        self.assertEqual(res_with_otp.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')

    # SMS provider failure tests
    @patch('bookings.sms_service.TwilioSMSProvider.is_configured', return_value=False)
    def test_unconfigured_sms_provider_returns_503(self, mock_is_conf):
        booking = self.create_booking()
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/send-pickup-otp/')
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('SMS service', res.data['error'])

    def test_mask_phone_utility(self):
        self.assertEqual(mask_phone('9876543210'), '******3210')
        self.assertEqual(mask_phone('+919876543210'), '+91 ******3210')
        self.assertEqual(normalize_to_e164('9876543210'), '+919876543210')
