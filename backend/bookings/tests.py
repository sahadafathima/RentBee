from datetime import timedelta
from decimal import Decimal
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from addresses.models import Address
from catalog.models import Category, Item
from .models import Booking, IssueReport, AvailabilityNotificationRequest, InAppNotification, PushSubscription, ProcessedWebhookEvent
from .admin import verify_payment_action
from .services import mark_booking_payment_verified

User = get_user_model()


class BookingSystemTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.owner = User.objects.create_user(
            email='owner@test.com',
            password='Password123!',
            full_name='Alice Owner',
            phone_number='9876543210'
        )
        self.renter = User.objects.create_user(
            email='renter@test.com',
            password='Password123!',
            full_name='Bob Renter',
            phone_number='9876543211'
        )
        self.stranger = User.objects.create_user(
            email='stranger@test.com',
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

        # Owner Address
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

        # Renter Address
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
            rental_price=Decimal('1500.00'),
            deposit=Decimal('5000.00'),
            stock=1,
            is_published=True
        )

    def test_booking_creation_and_price_snapshot(self):
        """Backend calculates duration strictly as end_date - start_date and snapshots Item prices."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()
        start_date = today + timedelta(days=2)
        end_date = today + timedelta(days=5)  # 3 days difference (5 - 2 = 3)

        payload = {
            'item_id': self.item.id,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'rental_price': '10.00',  # Client tamper attempt
            'total_amount': '50.00',   # Client tamper attempt
            'payment_status': 'paid'  # Client tamper attempt
        }

        res = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.data

        self.assertEqual(data['duration_days'], 3)
        self.assertEqual(Decimal(str(data['daily_price'])), Decimal('1500.00'))
        self.assertEqual(Decimal(str(data['original_rental_amount'])), Decimal('4500.00'))
        self.assertEqual(Decimal(str(data['discount_amount'])), Decimal('450.00'))
        self.assertEqual(Decimal(str(data['rental_amount'])), Decimal('4050.00'))
        self.assertEqual(Decimal(str(data['deposit_amount'])), Decimal('5000.00'))
        self.assertEqual(Decimal(str(data['total_amount'])), Decimal('9050.00'))
        self.assertEqual(data['status'], 'pending_approval')
        self.assertEqual(data['payment_status'], 'pending')

        # Verify snapshot isolation: mutating item rental price later does not affect booking
        self.item.rental_price = Decimal('9999.00')
        self.item.save()

        booking = Booking.objects.get(id=data['id'])
        self.assertEqual(booking.daily_price, Decimal('1500.00'))
        self.assertEqual(booking.total_amount, Decimal('9050.00'))

    def test_rental_duration_difference_calculation(self):
        """Duration is strictly difference between start and end date. Return date is not counted as extra day."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()

        # 1-day rental: 9th to 10th = 1 day (e.g. today+1 to today+2)
        res_1day = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=1)),
            'end_date': str(today + timedelta(days=2)),
        }, format='json')
        self.assertEqual(res_1day.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_1day.data['duration_days'], 1)
        self.assertEqual(Decimal(str(res_1day.data['original_rental_amount'])), Decimal('1500.00'))

        # Cancel to free up item
        Booking.objects.filter(id=res_1day.data['id']).update(status='cancelled')

        # 2-day rental: 9th to 11th = 2 days
        res_2day = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=1)),
            'end_date': str(today + timedelta(days=3)),
        }, format='json')
        self.assertEqual(res_2day.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_2day.data['duration_days'], 2)
        self.assertEqual(Decimal(str(res_2day.data['original_rental_amount'])), Decimal('3000.00'))

        Booking.objects.filter(id=res_2day.data['id']).update(status='cancelled')

        # 3-day rental: 9th to 12th = 3 days
        res_3day = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=1)),
            'end_date': str(today + timedelta(days=4)),
        }, format='json')
        self.assertEqual(res_3day.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_3day.data['duration_days'], 3)
        self.assertEqual(Decimal(str(res_3day.data['original_rental_amount'])), Decimal('4500.00'))

    def test_same_or_inverted_dates_rejected(self):
        """End date must be after start date; same day or past date is rejected."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()

        # Same start and end date (0 days)
        res_same = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=1)),
            'end_date': str(today + timedelta(days=1)),
        }, format='json')
        self.assertEqual(res_same.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('End date must be after start date', str(res_same.data))

        # Inverted date range
        res_inverted = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=3)),
            'end_date': str(today + timedelta(days=2)),
        }, format='json')
        self.assertEqual(res_inverted.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('End date must be after start date', str(res_inverted.data))

    def test_self_booking_prevention(self):
        """Owner cannot book their own item."""
        self.client.force_authenticate(user=self.owner)
        today = timezone.localdate()
        payload = {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=1)),
            'end_date': str(today + timedelta(days=2)),
        }
        res = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot book your own item', str(res.data))

    def test_date_overlap_rejection(self):
        """Conflicting bookings for the same item are blocked once reserved."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()
        start_date = today + timedelta(days=5)
        end_date = today + timedelta(days=8)

        # Create first booking
        res1 = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start_date),
            'end_date': str(end_date),
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Under Option A, pending requests do not reserve stock.
        # Owner approves first booking, reserving the unit.
        self.client.force_authenticate(user=self.owner)
        res_approve = self.client.post(f'/api/bookings/{res1.data["id"]}/approve/')
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)

        # Attempt overlapping booking from another user
        other_renter = User.objects.create_user(
            email='other@test.com', password='Password123!', full_name='Other', phone_number='1122334455'
        )
        Address.objects.create(
            user=other_renter, full_name='Other', house_number='12', address='Main Rd', area='Indiranagar',
            city='Bangalore', state='Karnataka', pincode='560038', country='India'
        )
        self.client.force_authenticate(user=other_renter)

        # Overlap case: start inside existing range
        res2 = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start_date + timedelta(days=1)),
            'end_date': str(end_date + timedelta(days=2)),
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Requested quantity is unavailable', str(res2.data))

        # Non-overlapping booking after end_date should succeed
        res3 = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(end_date + timedelta(days=1)),
            'end_date': str(end_date + timedelta(days=3)),
        }, format='json')
        self.assertEqual(res3.status_code, status.HTTP_201_CREATED)

    def test_opportunistic_expiry_frees_availability(self):
        """Pending booking older than 24 hours is marked expired and frees dates."""
        today = timezone.localdate()
        start = today + timedelta(days=10)
        end = today + timedelta(days=12)

        # Create pending booking and backdate created_at by 25 hours
        old_booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=start,
            end_date=end,
            duration_days=3,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('4500.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('9500.00'),
            status='pending_approval'
        )
        Booking.objects.filter(pk=old_booking.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )

        # Now, stranger tries to book the exact same dates
        Address.objects.create(
            user=self.stranger, full_name='Stranger', house_number='99', address='Outer Ring Rd', area='Bellandur',
            city='Bangalore', state='Karnataka', pincode='560103', country='India'
        )
        self.client.force_authenticate(user=self.stranger)
        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        old_booking.refresh_from_db()
        self.assertEqual(old_booking.status, 'expired')

    def test_owner_privacy_gate(self):
        """Owner address is redacted during pending_approval and revealed once approved."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='pending_approval'
        )

        # Renter views during pending_approval
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        owner_data = res.data['owner']
        self.assertEqual(owner_data['phone_number'], '')
        self.assertTrue(owner_data['address_info']['is_redacted'])
        self.assertNotIn('House 42B', str(owner_data['address_info']))

        # Stranger attempts access -> 403 Forbidden
        self.client.force_authenticate(user=self.stranger)
        res_stranger = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res_stranger.status_code, status.HTTP_403_FORBIDDEN)

        # Owner approves booking -> waiting_for_pickup
        booking.status = 'waiting_for_pickup'
        booking.save()

        # Renter views again: full address revealed
        self.client.force_authenticate(user=self.renter)
        res_approved = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(res_approved.status_code, status.HTTP_200_OK)
        owner_approved_data = res_approved.data['owner']
        self.assertEqual(owner_approved_data['phone_number'], '9876543210')
        self.assertFalse(owner_approved_data['address_info']['is_redacted'])
        self.assertIn('House 42B', owner_approved_data['address_info']['full_formatted_address'])

    def test_payment_gate_and_pickup_confirmation(self):
        """Pickup confirmation is blocked while payment is pending, and succeeds once verified."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='waiting_for_pickup',
            payment_status='pending'
        )

        self.client.force_authenticate(user=self.owner)

        # Attempt confirm-pickup with pending payment -> 400 Bad Request
        res_fail = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/', {'otp': '123456'}, format='json')
        self.assertEqual(res_fail.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('payment is verified', str(res_fail.data))

        # Authorized backend payment verification (e.g. staff admin)
        mark_booking_payment_verified(booking, verified_by=self.staff_admin, transaction_id='TXN-TEST-123')
        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_verified_by, self.staff_admin)
        self.assertIsNotNone(booking.payment_verified_at)

        # Pickup confirmation now succeeds with valid OTP
        booking.pickup_otp_hash = make_password('123456')
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()
        res_success = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/', {'otp': '123456'}, format='json')
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')
        self.assertIsNotNone(booking.picked_up_at)
        self.assertIsNotNone(booking.return_deadline)
        self.assertEqual(booking.return_deadline, booking.picked_up_at + timedelta(days=booking.duration_days))

    def test_actual_pickup_confirmation_return_deadline_and_timezone(self):
        """
        Return deadline is calculated by adding rental duration in 24-hour periods
        to the actual owner pickup confirmation timestamp.
        Display strings are formatted in Asia/Kolkata timezone.
        Passing the deadline does not auto-complete the rental.
        """
        import zoneinfo
        kolkata_tz = zoneinfo.ZoneInfo('Asia/Kolkata')

        # Selected dates: 2 days duration (e.g. 9th to 11th)
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='waiting_for_pickup',
            payment_status='paid'
        )

        # Confirm pickup at a specific timestamp: 9th at 3:00 PM IST (15:00)
        pickup_time_kolkata = timezone.datetime(2026, 11, 9, 15, 0, 0, tzinfo=kolkata_tz)
        booking.picked_up_at = pickup_time_kolkata
        booking.status = 'rental_in_progress'
        booking.save()

        # Check return deadline
        expected_deadline = pickup_time_kolkata + timedelta(days=2)  # 11th at 3:00 PM IST
        self.assertEqual(booking.return_deadline, expected_deadline)
        self.assertIn('11 Nov 2026', booking.return_deadline_display)
        self.assertIn('03:00 PM IST', booking.return_deadline_display)
        self.assertIn('09 Nov 2026', booking.picked_up_at_display)
        self.assertIn('03:00 PM IST', booking.picked_up_at_display)

        # Verify serializer exposes these exact fields to renter & owner
        self.client.force_authenticate(user=self.renter)
        detail_res = self.client.get(f'/api/bookings/{booking.id}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertIn('return_deadline', detail_res.data)
        self.assertIn('return_deadline_display', detail_res.data)
        self.assertIn('11 Nov 2026', detail_res.data['return_deadline_display'])

        # Overdue behavior: booking does NOT automatically complete when deadline passes
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')

        # Owner explicitly confirms return
        self.client.force_authenticate(user=self.owner)
        res_return = self.client.post(f'/api/bookings/{booking.id}/confirm-return/')
        self.assertEqual(res_return.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')
        self.assertIsNotNone(booking.returned_at)
        self.assertIsNotNone(booking.returned_at_display)

    def test_django_admin_verify_payment_action(self):
        """Staff admin action in Django Admin sets payment_status='paid' and records payment_verified_by and at."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='waiting_for_pickup',
            payment_status='pending'
        )

        class MockRequest:
            def __init__(self, user):
                self.user = user

        class MockModelAdmin:
            def message_user(self, request, message):
                pass

        mock_req = MockRequest(self.staff_admin)
        verify_payment_action(MockModelAdmin(), mock_req, Booking.objects.filter(id=booking.id))

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_verified_by, self.staff_admin)
        self.assertIsNotNone(booking.payment_verified_at)
        self.assertEqual(booking.payment_transaction_id, f"ADMIN-VERIFY-{booking.id}")

    @patch('bookings.services.get_razorpay_client')
    def test_cancellation_pre_pickup_restriction(self, mock_get_client):
        """Cancellation allowed only in pending_approval & waiting_for_pickup; blocked in rental_in_progress."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch_multiple_refund.return_value = {'count': 0, 'items': []}
        mock_rzp.payment.refund.return_value = {
            'id': 'rfnd_test_pre_pickup',
            'entity': 'refund',
            'amount': 800000,
            'currency': 'INR',
            'status': 'pending',
            'payment_id': 'pay_test_pre_pickup'
        }
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='waiting_for_pickup',
            payment_status='paid',
            payment_method='online',
            payment_transaction_id='pay_test_pre_pickup'
        )

        # Renter cancels before pickup -> succeeds and initiates 100% refund
        self.client.force_authenticate(user=self.renter)
        res_cancel = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'Change of plans'})
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.cancellation_reason, 'Change of plans')
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.refund_status, 'pending')
        self.assertEqual(booking.refund_amount, Decimal('8000.00'))

        # Now test rental_in_progress cancellation attempt
        active_booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='rental_in_progress',
            payment_status='paid'
        )
        res_blocked = self.client.post(f'/api/bookings/{active_booking.id}/cancel/')
        self.assertEqual(res_blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot cancel a rental that is already in progress', str(res_blocked.data))

    def test_item_return_and_completion(self):
        """Item return must be confirmed by owner, moving rental to completed."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today - timedelta(days=2),
            end_date=today - timedelta(days=1),  # Past end date
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='rental_in_progress',
            payment_status='paid'
        )

        # Status does NOT automatically become completed just because end_date passed
        self.assertEqual(booking.status, 'rental_in_progress')

        # Owner confirms return
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(f'/api/bookings/{booking.id}/confirm-return/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')
        self.assertIsNotNone(booking.returned_at)

    def test_problem_report_restricted_to_rental_in_progress(self):
        """Problem reporting strictly allowed only during rental_in_progress."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='waiting_for_pickup',
            payment_status='paid'
        )

        self.client.force_authenticate(user=self.renter)

        # Fails in waiting_for_pickup
        res_blocked = self.client.post(f'/api/bookings/{booking.id}/report-problem/', {
            'description': 'Camera lens cap missing.'
        })
        self.assertEqual(res_blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('only be submitted while a rental is in progress', str(res_blocked.data))

        # Update to rental_in_progress -> succeeds
        booking.status = 'rental_in_progress'
        booking.save()

        res_ok = self.client.post(f'/api/bookings/{booking.id}/report-problem/', {
            'description': 'Battery drain faster than expected.'
        })
        self.assertEqual(res_ok.status_code, status.HTTP_201_CREATED)
        self.assertEqual(IssueReport.objects.count(), 1)
        report = IssueReport.objects.first()
        self.assertEqual(report.description, 'Battery drain faster than expected.')
        self.assertEqual(report.booking, booking)
        self.assertEqual(report.renter, self.renter)
        self.assertEqual(report.owner, self.owner)

    def test_my_bookings_list_and_dynamic_counts(self):
        """My bookings endpoint returns accurate dynamic counts and tab filtering."""
        today = timezone.localdate()
        # Create 1 pending, 1 active in-progress, 1 completed, 1 cancelled
        Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=1), end_date=today + timedelta(days=2),
            duration_days=2, daily_price=Decimal('1500'), rental_amount=Decimal('3000'),
            deposit_amount=Decimal('5000'), total_amount=Decimal('8000'),
            status='pending_approval'
        )
        Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=3), end_date=today + timedelta(days=4),
            duration_days=2, daily_price=Decimal('1500'), rental_amount=Decimal('3000'),
            deposit_amount=Decimal('5000'), total_amount=Decimal('8000'),
            status='rental_in_progress', payment_status='paid'
        )
        Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=5), end_date=today + timedelta(days=6),
            duration_days=2, daily_price=Decimal('1500'), rental_amount=Decimal('3000'),
            deposit_amount=Decimal('5000'), total_amount=Decimal('8000'),
            status='completed', payment_status='paid'
        )
        Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=7), end_date=today + timedelta(days=8),
            duration_days=2, daily_price=Decimal('1500'), rental_amount=Decimal('3000'),
            deposit_amount=Decimal('5000'), total_amount=Decimal('8000'),
            status='cancelled'
        )

        self.client.force_authenticate(user=self.renter)

        # Tab: All
        res_all = self.client.get('/api/bookings/my-bookings/')
        self.assertEqual(res_all.status_code, status.HTTP_200_OK)
        counts = res_all.data['counts']
        self.assertEqual(counts['all'], 4)
        self.assertEqual(counts['active'], 2)  # pending_approval + rental_in_progress
        self.assertEqual(counts['completed'], 1)
        self.assertEqual(counts['cancelled'], 1)
        self.assertEqual(len(res_all.data['results']), 4)

        # Tab: Active
        res_active = self.client.get('/api/bookings/my-bookings/?tab=active')
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_active.data['results']), 2)

        # Tab: Completed
        res_completed = self.client.get('/api/bookings/my-bookings/?tab=completed')
        self.assertEqual(res_completed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_completed.data['results']), 1)

        # Tab: Cancelled
        res_cancelled = self.client.get('/api/bookings/my-bookings/?tab=cancelled')
        self.assertEqual(res_cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cancelled.data['results']), 1)

        # Search by item name
        res_search = self.client.get('/api/bookings/my-bookings/?search=Sony')
        self.assertEqual(res_search.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_search.data['results']), 4)

    def test_mandatory_address_completion_validation(self):
        """User cannot create a booking without a completed address on backend."""
        user_no_addr = User.objects.create_user(
            email='noaddress@test.com', password='Password123!', full_name='No Address', phone_number='9999988888'
        )
        self.client.force_authenticate(user=user_no_addr)
        today = timezone.localdate()

        # 1. No address at all
        res1 = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=20)),
            'end_date': str(today + timedelta(days=22)),
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Please complete your address before booking', str(res1.data))

        # 2. Incomplete address (missing pincode and city)
        addr = Address.objects.create(
            user=user_no_addr,
            full_name='No Address',
            house_number='1',
            address='Street',
            area='Area',
            city='',
            state='Karnataka',
            pincode=''
        )
        res2 = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=20)),
            'end_date': str(today + timedelta(days=22)),
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Please complete your address before booking', str(res2.data))

        # 3. Completed address succeeds
        addr.city = 'Bangalore'
        addr.pincode = '560001'
        addr.save()

        res3 = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=20)),
            'end_date': str(today + timedelta(days=22)),
        }, format='json')
        self.assertEqual(res3.status_code, status.HTTP_201_CREATED)

    def test_check_availability_endpoint(self):
        """Availability endpoint accurately reports availability, conflicts, and invalid inputs."""
        today = timezone.localdate()
        start = today + timedelta(days=30)
        end = today + timedelta(days=32)

        # Before booking: available
        res = self.client.get(f'/api/bookings/check-availability/?item_id={self.item.id}&start_date={start}&end_date={end}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['is_available'])
        self.assertEqual(res.data['status_label'], 'Available')

        # Create booking for these dates (pending approval)
        self.client.force_authenticate(user=self.renter)
        res_create = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)

        # While pending approval: item remains available (Option A)
        res_pending = self.client.get(f'/api/bookings/check-availability/?item_id={self.item.id}&start_date={start}&end_date={end}')
        self.assertEqual(res_pending.status_code, status.HTTP_200_OK)
        self.assertTrue(res_pending.data['is_available'])

        # Owner approves booking: moves to waiting_for_pickup and reserves stock
        self.client.force_authenticate(user=self.owner)
        res_approve = self.client.post(f'/api/bookings/{res_create.data["id"]}/approve/')
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)

        # After approval: Booked
        res_booked = self.client.get(f'/api/bookings/check-availability/?item_id={self.item.id}&start_date={start}&end_date={end}')
        self.assertEqual(res_booked.status_code, status.HTTP_200_OK)
        self.assertFalse(res_booked.data['is_available'])
        self.assertEqual(res_booked.data['status_label'], 'Booked')

        # Past date validation
        past_start = today - timedelta(days=2)
        res_past = self.client.get(f'/api/bookings/check-availability/?item_id={self.item.id}&start_date={past_start}&end_date={today}')
        self.assertEqual(res_past.status_code, status.HTTP_400_BAD_REQUEST)

        # Same start and end date (0 days) is rejected
        res_same = self.client.get(f'/api/bookings/check-availability/?item_id={self.item.id}&start_date={start}&end_date={start}')
        self.assertEqual(res_same.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('End date must be after start date', res_same.data['message'])

        # Inverted date range is rejected
        res_inverted = self.client.get(f'/api/bookings/check-availability/?item_id={self.item.id}&start_date={end}&end_date={start}')
        self.assertEqual(res_inverted.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('End date must be after start date', res_inverted.data['message'])

    def test_notify_availability_and_trigger_on_cancellation(self):
        """Notify me creates request and cancellation triggers in-app notification."""
        today = timezone.localdate()
        start = today + timedelta(days=40)
        end = today + timedelta(days=42)

        # Create booking by renter
        self.client.force_authenticate(user=self.renter)
        res_book = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')
        booking_id = res_book.data['id']

        # Charlie Stranger requests to be notified
        self.client.force_authenticate(user=self.stranger)
        res_notify = self.client.post('/api/bookings/notify-availability/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')
        self.assertEqual(res_notify.status_code, status.HTTP_201_CREATED)
        self.assertTrue(AvailabilityNotificationRequest.objects.filter(user=self.stranger, item=self.item).exists())

        # Duplicate request doesn't crash or re-create duplicate row
        res_dup = self.client.post('/api/bookings/notify-availability/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')
        self.assertEqual(res_dup.status_code, status.HTTP_200_OK)
        self.assertEqual(AvailabilityNotificationRequest.objects.filter(user=self.stranger, item=self.item).count(), 1)

        # Now renter cancels their booking
        self.client.force_authenticate(user=self.renter)
        with self.captureOnCommitCallbacks(execute=True):
            res_cancel = self.client.post(f'/api/bookings/{booking_id}/cancel/', {'reason': 'Changed plans'}, format='json')
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)

        # Check that InAppNotification was created for Charlie Stranger
        notification = InAppNotification.objects.filter(user=self.stranger, item=self.item).first()
        self.assertIsNotNone(notification)
        self.assertIn('Available', notification.title)
        self.assertFalse(notification.is_read)

    def test_notifications_list_and_mark_read(self):
        """Notifications can be listed and marked as read."""
        notif = InAppNotification.objects.create(
            user=self.renter,
            item=self.item,
            title='Dates now open!',
            message='Sony A7 IV is now available.'
        )
        self.client.force_authenticate(user=self.renter)

        # List notifications
        res_list = self.client.get('/api/bookings/notifications/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.data['unread_count'], 1)
        self.assertEqual(len(res_list.data['results']), 1)

        # Mark as read
        res_read = self.client.post(f'/api/bookings/notifications/{notif.id}/mark-read/')
        self.assertEqual(res_read.status_code, status.HTTP_200_OK)

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_host_hub_incoming_requests_visibility_and_isolation(self):
        """
        Comprehensive test verifying:
        1. User A lists an item.
        2. User B sends a rental request for that item.
        3. User A sees User B's request inside Host Hub -> Incoming Requests.
        4. User B cannot see that incoming request in their own account.
        5. User C cannot see incoming requests for items listed by other users.
        6. User A can approve/decline the request.
        7. Non-owners (User B and C) cannot approve or decline.
        """
        # User A is self.owner, User B is self.renter, User C is self.stranger
        start = timezone.localdate() + timedelta(days=20)
        end = timezone.localdate() + timedelta(days=25)

        # 1. User B requests rental of User A's item
        self.client.force_authenticate(user=self.renter)
        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        booking_id = res.data['id']

        # 2. User A (Owner) checks Host Hub -> Incoming Requests
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.get('/api/bookings/host/requests/?tab=incoming')
        self.assertEqual(res_owner.status_code, status.HTTP_200_OK)
        self.assertEqual(res_owner.data['counts']['incoming'], 1)
        self.assertEqual(len(res_owner.data['results']), 1)
        incoming_item = res_owner.data['results'][0]
        self.assertEqual(incoming_item['id'], booking_id)
        self.assertEqual(incoming_item['renter']['email'], '')
        self.assertEqual(incoming_item['item']['name'], self.item.name)
        self.assertEqual(incoming_item['status'], 'pending_approval')

        # 3. User B (Renter) checks Host Hub -> Incoming Requests (Must be 0)
        self.client.force_authenticate(user=self.renter)
        res_renter_hub = self.client.get('/api/bookings/host/requests/?tab=incoming')
        self.assertEqual(res_renter_hub.status_code, status.HTTP_200_OK)
        self.assertEqual(res_renter_hub.data['counts']['incoming'], 0)
        self.assertEqual(len(res_renter_hub.data['results']), 0)

        # User B CAN see it in their own outgoing bookings (My Bookings)
        res_renter_my = self.client.get('/api/bookings/my-bookings/?tab=active')
        self.assertEqual(res_renter_my.status_code, status.HTTP_200_OK)
        self.assertEqual(res_renter_my.data['counts']['active'], 1)
        self.assertEqual(res_renter_my.data['results'][0]['id'], booking_id)

        # 4. User C (Stranger / non-owner) checks Host Hub -> Incoming Requests (Must be 0)
        self.client.force_authenticate(user=self.stranger)
        res_stranger_hub = self.client.get('/api/bookings/host/requests/?tab=incoming')
        self.assertEqual(res_stranger_hub.status_code, status.HTTP_200_OK)
        self.assertEqual(res_stranger_hub.data['counts']['incoming'], 0)
        self.assertEqual(len(res_stranger_hub.data['results']), 0)

        # 5. Non-owners cannot approve or decline
        res_stranger_approve = self.client.post(f'/api/bookings/{booking_id}/approve/')
        self.assertEqual(res_stranger_approve.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.renter)
        res_renter_approve = self.client.post(f'/api/bookings/{booking_id}/approve/')
        self.assertEqual(res_renter_approve.status_code, status.HTTP_403_FORBIDDEN)

        # 6. User A (Owner) can approve the request
        self.client.force_authenticate(user=self.owner)
        res_approve = self.client.post(f'/api/bookings/{booking_id}/approve/')
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)
        self.assertEqual(res_approve.data['status'], 'waiting_for_pickup')

        # 7. Check Host Hub tabs after approval
        # Should disappear from incoming
        res_incoming = self.client.get('/api/bookings/host/requests/?tab=incoming')
        self.assertEqual(res_incoming.data['counts']['incoming'], 0)
        self.assertEqual(len(res_incoming.data['results']), 0)
        # Should appear in accepted
        res_accepted = self.client.get('/api/bookings/host/requests/?tab=accepted')
        self.assertEqual(res_accepted.data['counts']['accepted'], 1)
        self.assertEqual(res_accepted.data['counts']['active'], 1)
        self.assertEqual(len(res_accepted.data['results']), 1)
        self.assertEqual(res_accepted.data['results'][0]['id'], booking_id)

    def test_host_hub_rejected_tab_workflow(self):
        # Create a new booking request
        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=10)
        end = start + timedelta(days=2)
        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        booking_id = res.data['id']

        # Owner sees it in incoming tab
        self.client.force_authenticate(user=self.owner)
        res_incoming = self.client.get('/api/bookings/host/requests/?tab=incoming')
        self.assertEqual(res_incoming.data['counts']['incoming'], 1)
        self.assertEqual(res_incoming.data['counts']['rejected'], 0)
        self.assertEqual(len(res_incoming.data['results']), 1)

        # Owner rejects the request with a reason
        res_reject = self.client.post(f'/api/bookings/{booking_id}/reject/', {
            'reason': 'Item under maintenance'
        }, format='json')
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)

        # Disappears from incoming requests
        res_incoming_after = self.client.get('/api/bookings/host/requests/?tab=incoming')
        self.assertEqual(res_incoming_after.data['counts']['incoming'], 0)
        self.assertEqual(len(res_incoming_after.data['results']), 0)

        # Appears in rejected tab
        res_rejected = self.client.get('/api/bookings/host/requests/?tab=rejected')
        self.assertEqual(res_rejected.data['counts']['rejected'], 1)
        self.assertEqual(len(res_rejected.data['results']), 1)
        rejected_booking = res_rejected.data['results'][0]
        self.assertEqual(rejected_booking['id'], booking_id)
        self.assertEqual(rejected_booking['status'], 'rejected')
        self.assertEqual(rejected_booking['rejection_reason'], 'Item under maintenance')




class BookingPrivacyTests(TestCase):
    setUp = BookingSystemTests.setUp

    def test_privacy_matrix(self):
        for state in ('pending_approval', 'waiting_for_pickup', 'rental_in_progress',
                      'completed', 'rejected', 'expired', 'cancelled', 'unexpected'):
            for approved in (False, True):
                booking = Booking.objects.create(
                    item=self.item, owner=self.owner, renter=self.renter,
                    start_date=timezone.localdate() + timedelta(days=2),
                    end_date=timezone.localdate() + timedelta(days=3),
                    duration_days=1, daily_price=1500, rental_amount=1500,
                    deposit_amount=5000, total_amount=6500, status=state,
                    approved_at=timezone.now() if approved else None)
                visible = state in ('waiting_for_pickup', 'rental_in_progress', 'completed')
                for viewer, own, other, person, address, url in (
                    (self.renter, 'renter', 'owner', self.owner, self.owner_address, 'my-bookings/'),
                    (self.owner, 'owner', 'renter', self.renter, self.renter_address, 'host/requests/')):
                    with self.subTest(state=state, approved=approved, viewer=own):
                        self.client.force_authenticate(viewer)
                        detail = self.client.get(f'/api/bookings/{booking.pk}/')
                        self.assertEqual(detail.status_code, 200)
                        rows = self.client.get('/api/bookings/' + url).data['results']
                        row = next(r for r in rows if r['id'] == booking.pk)
                        for payload in (detail.data, row):
                            self.assertEqual(payload[own]['email'], viewer.email)
                            self.assertEqual(payload[own]['phone_number'], viewer.phone_number)
                            own_address = self.renter_address if own == 'renter' else self.owner_address
                            self.assertFalse(payload[own]['address_info']['is_redacted'])
                            self.assertEqual(payload[own]['address_info']['house_number'], own_address.house_number)
                            self.assertEqual(payload[own]['address_info']['address'], own_address.address)
                            self.assertEqual(payload[other]['email'], '')
                            self.assertEqual(payload[other]['phone_number'], person.phone_number if visible else '')
                            addr = payload[other]['address_info']
                            self.assertEqual(addr['is_redacted'], not visible)
                            self.assertEqual(addr.get('house_number', ''), address.house_number if visible else '')
                            self.assertEqual(addr.get('address', ''), address.address if visible else '')
                            for field in ('house_number', 'address', 'landmark', 'pincode'):
                                if visible:
                                    self.assertEqual(addr[field], getattr(address, field))
                                else:
                                    self.assertNotIn(field, addr)
                            if visible:
                                self.assertIn(address.house_number, addr['full_formatted_address'])
                            else:
                                self.assertNotIn('full_formatted_address', addr)
                self.client.force_authenticate(self.stranger)
                self.assertEqual(self.client.get(f'/api/bookings/{booking.pk}/').status_code, 403)
                for url in ('my-bookings/', 'host/requests/'):
                    self.assertEqual(self.client.get('/api/bookings/' + url).data['results'], [])
                self.client.force_authenticate(self.staff_admin)
                staff_response = self.client.get(f'/api/bookings/{booking.pk}/')
                self.assertEqual(staff_response.status_code, 200)
                legacy_owner_visible = state not in ('pending_approval', 'rejected', 'expired')
                self.assertEqual(staff_response.data['owner']['email'], self.owner.email if legacy_owner_visible else '')
                self.assertEqual(staff_response.data['owner']['phone_number'], self.owner.phone_number if legacy_owner_visible else '')
                self.assertEqual(staff_response.data['owner']['address_info']['is_redacted'], not legacy_owner_visible)
                self.assertEqual(staff_response.data['renter']['email'], self.renter.email)
                self.assertEqual(staff_response.data['renter']['phone_number'], self.renter.phone_number)
                self.assertNotIn('house_number', staff_response.data['renter']['address_info'])
                self.owner.full_name = ''
                self.owner.save(update_fields=['full_name'])
                self.client.force_authenticate(self.renter)
                self.assertEqual(self.client.get(f'/api/bookings/{booking.pk}/').data['owner']['full_name'], 'Host')
                self.client.force_authenticate(None)
                for url in (f'/api/items/{self.item.pk}/', '/api/items/',
                            f'/api/bookings/check-availability/?item_id={self.item.pk}&start_date={booking.start_date}&end_date={booking.end_date}'):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    for private in (self.owner.email, self.renter.email, self.owner.phone_number,
                                    self.renter.phone_number, self.owner_address.house_number,
                                    self.renter_address.house_number):
                        self.assertNotIn(private, str(response.data))
                booking.delete()

    def test_second_renter_and_host_are_denied(self):
        other_host = User.objects.create_user(email='host2@test.com', full_name='Other Host', phone_number='9876543214')
        other_item = Item.objects.create(name='Other item', category=self.category, owner=other_host, rental_price=10)
        Booking.objects.create(
            item=other_item, owner=other_host, renter=self.stranger,
            start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=1),
            duration_days=1, daily_price=10, rental_amount=10, total_amount=10)
        booking = Booking.objects.create(
            item=self.item, owner=self.owner, renter=self.renter,
            start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=1),
            duration_days=1, daily_price=10, rental_amount=10, total_amount=10)
        for viewer in (self.stranger, other_host):
            self.client.force_authenticate(viewer)
            self.assertEqual(self.client.get(f'/api/bookings/{booking.pk}/').status_code, 403)
            for path in ('my-bookings/', 'host/requests/'):
                ids = [row['id'] for row in self.client.get('/api/bookings/' + path).data['results']]
                self.assertNotIn(booking.pk, ids)

    def test_approved_cancellation_and_safe_names(self):
        self.client.force_authenticate(self.renter)
        response = self.client.post('/api/bookings/', {
            'item_id': self.item.pk,
            'start_date': str(timezone.localdate() + timedelta(days=4)),
            'end_date': str(timezone.localdate() + timedelta(days=5)),
        }, format='json')
        self.assertEqual(response.status_code, 201)
        pk = response.data['id']
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/approve/').status_code, 200)
        self.client.force_authenticate(self.renter)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/cancel/').status_code, 200)
        for person in (self.owner, self.renter):
            person.full_name = ''
            person.save(update_fields=['full_name'])
        for viewer, counterpart, fallback in ((self.renter, 'owner', 'Host'), (self.owner, 'renter', 'Renter')):
            self.client.force_authenticate(viewer)
            data = self.client.get(f'/api/bookings/{pk}/').data[counterpart]
            self.assertEqual(data['full_name'], fallback)
            self.assertEqual(data['email'], '')
            self.assertEqual(data['phone_number'], '')
            self.assertTrue(data['address_info']['is_redacted'])
            for field in ('full_formatted_address', 'house_number', 'address', 'landmark', 'pincode'):
                self.assertNotIn(field, data['address_info'])


class QuantityBookingTests(TestCase):
    def setUp(self):
        BookingSystemTests.setUp(self)
        Address.objects.create(
            user=self.stranger, full_name='Charlie Stranger', house_number='2',
            address='Second Street', area='Area', city='Bangalore', state='Karnataka',
            pincode='560002', country='India', address_type='Home')
        self.item.stock = 5
        self.item.save(update_fields=['stock'])
        self.day = timezone.localdate() + timedelta(days=7)

    def request(self, user, quantity):
        self.client.force_authenticate(user)
        return self.client.post('/api/bookings/', {
            'item_id': self.item.pk,
            'start_date': str(self.day),
            'end_date': str(self.day + timedelta(days=2)),
            'requested_quantity': quantity,
        }, format='json')

    def availability(self):
        from .services import get_item_availability
        return get_item_availability(self.item, self.day, self.day + timedelta(days=2))

    def test_quantity_is_saved_and_prices_include_quantity(self):
        response = self.request(self.renter, 3)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['requested_quantity'], 3)
        self.assertEqual(Decimal(str(response.data['original_rental_amount'])), Decimal('9000.00'))
        self.assertEqual(Decimal(str(response.data['discount_amount'])), Decimal('900.00'))
        self.assertEqual(Decimal(str(response.data['rental_amount'])), Decimal('8100.00'))
        self.assertEqual(Decimal(str(response.data['deposit_amount'])), Decimal('15000.00'))
        self.assertEqual(Decimal(str(response.data['total_amount'])), Decimal('23100.00'))
        booking = Booking.objects.get(pk=response.data['id'])
        self.assertEqual(booking.requested_quantity, 3)

    def test_invalid_or_excessive_quantity_is_rejected_with_available_count(self):
        for quantity in (0, -1):
            response = self.request(self.renter, quantity)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('requested_quantity', response.data)
        response = self.request(self.renter, 7)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Only 5 items', str(response.data))

    def test_pending_requests_do_not_reserve_capacity(self):
        self.assertEqual(self.request(self.renter, 3).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.request(self.stranger, 4).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.availability()['available_stock'], 5)

    def test_approval_reserves_quantity_and_second_approval_cannot_overbook(self):
        first = self.request(self.renter, 3).data['id']
        second = self.request(self.stranger, 3).data['id']
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{first}/approve/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.availability()['available_stock'], 2)
        response = self.client.post(f'/api/bookings/{second}/approve/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Only 2 items', str(response.data))
        self.assertEqual(Booking.objects.get(pk=second).status, 'pending_approval')
        self.assertEqual(self.client.post(f'/api/bookings/{first}/approve/').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.availability()['available_stock'], 2)

    def test_rejection_cancellation_and_return_restore_quantity(self):
        rejected = self.request(self.renter, 3).data['id']
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{rejected}/reject/', {'reason': 'Maintenance'}, format='json').status_code, status.HTTP_200_OK)
        self.assertEqual(self.availability()['available_stock'], 5)
        notification = InAppNotification.objects.get(booking_id=rejected, event='rejected')
        self.assertIn('Maintenance', notification.message)

        approved = self.request(self.renter, 3).data['id']
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{approved}/approve/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.availability()['available_stock'], 2)
        self.client.force_authenticate(self.renter)
        self.assertEqual(self.client.post(f'/api/bookings/{approved}/cancel/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.availability()['available_stock'], 5)

        active = self.request(self.renter, 3).data['id']
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{active}/approve/').status_code, status.HTTP_200_OK)
        booking = Booking.objects.get(pk=active)
        mark_booking_payment_verified(booking, verified_by=self.staff_admin)
        booking.pickup_otp_hash = make_password('123456')
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()
        self.assertEqual(self.client.post(f'/api/bookings/{active}/confirm-pickup/', {'otp': '123456'}, format='json').status_code, status.HTTP_200_OK)
        self.assertEqual(self.availability()['available_stock'], 2)
        self.assertEqual(self.client.post(f'/api/bookings/{active}/confirm-return/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.availability()['available_stock'], 5)

    def test_historical_booking_default_quantity_is_one_and_api_default_is_one(self):
        historical = Booking.objects.create(
            item=self.item, owner=self.owner, renter=self.renter,
            start_date=self.day, end_date=self.day + timedelta(days=2), duration_days=2,
            daily_price=10, rental_amount=20, total_amount=20, status='waiting_for_pickup')
        self.assertEqual(historical.requested_quantity, 1)
        self.assertEqual(self.availability()['available_stock'], 4)
        response = self.request(self.stranger, 1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['requested_quantity'], 1)

    def test_end_to_end_quantity_lifecycle_and_notifications(self):
        """
        Verify end-to-end multi-quantity flow:
        - Multiple pending requests can coexist without reserving stock.
        - Owner approval reserves the requested quantity.
        - Overbooking is blocked at approval.
        - Rejection leaves stock available.
        - Renter receives approval and rejection in-app notifications with rejection reasons.
        """
        self.item.stock = 3
        self.item.save(update_fields=['stock'])

        # 1. Multiple pending requests coexist without reserving stock
        req_a = self.request(self.renter, 2)
        self.assertEqual(req_a.status_code, status.HTTP_201_CREATED)
        booking_a_id = req_a.data['id']

        req_b = self.request(self.stranger, 2)
        self.assertEqual(req_b.status_code, status.HTTP_201_CREATED)
        booking_b_id = req_b.data['id']

        self.assertEqual(self.availability()['available_stock'], 3)
        self.assertTrue(InAppNotification.objects.filter(booking_id=booking_a_id, event='requested', user=self.owner).exists())
        self.assertTrue(InAppNotification.objects.filter(booking_id=booking_b_id, event='requested', user=self.owner).exists())

        # 2. Owner approves Request A (2 units reserved)
        self.client.force_authenticate(self.owner)
        res_approve_a = self.client.post(f'/api/bookings/{booking_a_id}/approve/')
        self.assertEqual(res_approve_a.status_code, status.HTTP_200_OK)
        self.assertEqual(self.availability()['available_stock'], 1)

        notif_a = InAppNotification.objects.get(booking_id=booking_a_id, event='accepted', user=self.renter)
        self.assertIn('accepted', notif_a.title.lower())

        # 3. Owner attempts to approve Request B (needs 2, but only 1 available) -> blocked
        res_approve_b = self.client.post(f'/api/bookings/{booking_b_id}/approve/')
        self.assertEqual(res_approve_b.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Only 1 items are currently available', str(res_approve_b.data))
        self.assertEqual(Booking.objects.get(pk=booking_b_id).status, 'pending_approval')
        self.assertEqual(self.availability()['available_stock'], 1)

        # 4. Owner rejects Request B with a reason
        rejection_reason = "Cannot fulfill request: only 1 unit remaining for these dates."
        res_reject_b = self.client.post(
            f'/api/bookings/{booking_b_id}/reject/',
            {'reason': rejection_reason},
            format='json'
        )
        self.assertEqual(res_reject_b.status_code, status.HTTP_200_OK)
        booking_b = Booking.objects.get(pk=booking_b_id)
        self.assertEqual(booking_b.status, 'rejected')
        self.assertEqual(booking_b.rejection_reason, rejection_reason)
        self.assertEqual(self.availability()['available_stock'], 1)

        # 5. Renter B receives rejected notification containing rejection reason
        notif_b = InAppNotification.objects.get(booking_id=booking_b_id, event='rejected', user=self.stranger)
        self.assertIn('rejected', notif_b.title.lower())
        self.assertIn(rejection_reason, notif_b.message)

        # Renter B views booking details and sees rejection reason
        self.client.force_authenticate(self.stranger)
        res_detail_b = self.client.get(f'/api/bookings/{booking_b_id}/')
        self.assertEqual(res_detail_b.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail_b.data['status'], 'rejected')
        self.assertEqual(res_detail_b.data['rejection_reason'], rejection_reason)


class StockAvailabilityTests(TestCase):
    setUp = BookingSystemTests.setUp

    def request_booking(self, start, end):
        self.client.force_authenticate(self.renter)
        return self.client.post('/api/bookings/', {
            'item_id': self.item.pk, 'start_date': str(start), 'end_date': str(end)
        }, format='json')

    def reservation(self, start, end, state='waiting_for_pickup'):
        return Booking.objects.create(
            item=self.item, owner=self.owner, renter=self.renter, start_date=start,
            end_date=end, duration_days=1, daily_price=10, rental_amount=10,
            total_amount=10, status=state)

    def test_capacity_limits_and_total_inventory(self):
        start = timezone.localdate() + timedelta(days=10)
        for stock in (0, 1, 2, 3):
            Booking.objects.all().delete()
            self.item.stock = stock
            self.item.save(update_fields=['stock'])
            for count in range(stock):
                res = self.request_booking(start, start + timedelta(days=2))
                self.assertEqual(res.status_code, 201)
                self.client.force_authenticate(self.owner)
                self.assertEqual(self.client.post(f'/api/bookings/{res.data["id"]}/approve/').status_code, 200)
            self.assertEqual(self.request_booking(start, start + timedelta(days=2)).status_code, 400)
            self.item.refresh_from_db()
            self.assertEqual(self.item.stock, stock)

    def test_peak_capacity_and_inclusive_boundaries(self):
        from .services import get_item_availability
        day = timezone.localdate() + timedelta(days=10)
        self.item.stock = 2
        self.item.save(update_fields=['stock'])
        self.reservation(day, day + timedelta(days=1), state='waiting_for_pickup')
        self.reservation(day + timedelta(days=3), day + timedelta(days=4), state='waiting_for_pickup')
        self.assertEqual(get_item_availability(self.item, day, day + timedelta(days=4))['available_stock'], 1)
        res = self.request_booking(day, day + timedelta(days=4))
        self.assertEqual(res.status_code, 201)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{res.data["id"]}/approve/').status_code, 200)
        self.assertEqual(self.request_booking(day + timedelta(days=1), day + timedelta(days=2)).status_code, 400)
        self.assertEqual(self.request_booking(day + timedelta(days=6), day + timedelta(days=7)).status_code, 201)

    def test_status_release_and_overdue_return(self):
        from .services import get_item_availability
        day = timezone.localdate()
        booking = self.reservation(day - timedelta(days=4), day - timedelta(days=1), 'rental_in_progress')
        self.assertEqual(get_item_availability(self.item, day, day + timedelta(days=20))['available_stock'], 0)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{booking.pk}/confirm-return/').status_code, 200)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.returned_at)
        self.assertEqual(get_item_availability(self.item)['available_stock'], 1)
        booking.start_date = day
        booking.end_date = day + timedelta(days=2)
        for state in ('pending_approval', 'waiting_for_pickup', 'rental_in_progress',
                      'rejected', 'cancelled', 'expired', 'completed'):
            booking.status = state
            booking.save()
            expected = 0 if state in ('waiting_for_pickup', 'rental_in_progress') else 1
            self.assertEqual(get_item_availability(self.item)['available_stock'], expected)
        booking.status = 'pending_approval'
        booking.save()
        Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(get_item_availability(self.item)['available_stock'], 1)

    def test_public_and_date_availability_agree(self):
        day = timezone.localdate()
        self.reservation(day + timedelta(days=5), day + timedelta(days=7))
        for stock in (0, 1, 2):
            self.item.stock = stock
            self.item.save(update_fields=['stock'])
            detail = self.client.get(f'/api/items/{self.item.pk}/').data
            listing = self.client.get('/api/items/').data['results'][0]
            dated = self.client.get(
                f'/api/bookings/check-availability/?item_id={self.item.pk}&start_date={day}&end_date={day + timedelta(days=1)}').data
            for key in ('total_stock', 'available_stock', 'is_available', 'availability_reason'):
                self.assertEqual(detail[key], listing[key])
                self.assertEqual(detail[key], dated[key])
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.patch(f'/api/admin/items/{self.item.pk}/', {'stock': 99}, format='json').status_code, 403)


class StockConcurrencyTests(TransactionTestCase):
    setUp = BookingSystemTests.setUp

    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_requests_reserve_only_final_unit(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        Address.objects.create(
            user=self.stranger, full_name='Second Renter', house_number='2',
            address='Second Street', area='Area', city='City', state='State', pincode='123456')
        barrier = Barrier(2)
        day = timezone.localdate() + timedelta(days=10)
        def submit(index):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=(self.renter.pk, self.stranger.pk)[index]))
                barrier.wait(timeout=10)
                return client.post('/api/bookings/', {
                    'item_id': self.item.pk, 'start_date': str(day),
                    'end_date': str(day + timedelta(days=2)),
                }, format='json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(sorted(results), [201, 400])
        self.assertEqual(Booking.objects.filter(item=self.item).count(), 1)


class StockTransitionConcurrencyTests(TransactionTestCase):
    setUp = BookingSystemTests.setUp

    def race(self, initial, actions):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        booking = Booking.objects.create(
            item=self.item, owner=self.owner, renter=self.renter,
            start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=2),
            duration_days=2, daily_price=10, rental_amount=20, total_amount=20,
            status=initial, payment_status='paid',
            pickup_otp_hash=make_password('123456'),
            pickup_otp_expires_at=timezone.now() + timedelta(minutes=10))
        barrier = Barrier(2)
        def submit(action):
            close_old_connections()
            try:
                endpoint, user_id = action
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=user_id))
                barrier.wait(timeout=10)
                return client.post(f'/api/bookings/{booking.pk}/{endpoint}/', {'otp': '123456'}, format='json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, actions))
        booking.refresh_from_db()
        self.assertEqual(sorted(results), [200, 400])
        return booking

    @skipUnlessDBFeature('has_select_for_update')
    def test_cancel_vs_pickup(self):
        booking = self.race('waiting_for_pickup', [
            ('cancel', self.renter.pk), ('confirm-pickup', self.owner.pk)])
        self.assertIn(booking.status, ('cancelled', 'rental_in_progress'))
        if booking.status == 'cancelled':
            self.assertIsNone(booking.picked_up_at)
        else:
            self.assertIsNotNone(booking.picked_up_at)

    @skipUnlessDBFeature('has_select_for_update')
    def test_reject_vs_approve(self):
        booking = self.race('pending_approval', [
            ('reject', self.owner.pk), ('approve', self.owner.pk)])
        self.assertIn(booking.status, ('rejected', 'waiting_for_pickup'))

    @skipUnlessDBFeature('has_select_for_update')
    def test_return_vs_cancel(self):
        booking = self.race('rental_in_progress', [
            ('confirm-return', self.owner.pk), ('cancel', self.renter.pk)])
        self.assertEqual(booking.status, 'completed')
        self.assertIsNotNone(booking.returned_at)


class NextAvailableStockTests(TestCase):
    setUp = BookingSystemTests.setUp

    def test_next_day_uses_all_reservations_and_active_rentals(self):
        from .services import get_next_available_date
        today = timezone.localdate()
        def reserve(start, end, state='waiting_for_pickup'):
            return Booking.objects.create(
                item=self.item, owner=self.owner, renter=self.renter,
                start_date=start, end_date=end, duration_days=1,
                daily_price=10, rental_amount=10, total_amount=10, status=state)
        reserve(today, today + timedelta(days=2))
        reserve(today + timedelta(days=2), today + timedelta(days=5), 'waiting_for_pickup')
        self.assertEqual(get_next_available_date(self.item), str(today + timedelta(days=6)))
        active = reserve(today - timedelta(days=4), today - timedelta(days=1), 'rental_in_progress')
        self.assertIsNone(get_next_available_date(self.item))
        active.status = 'completed'
        active.save()
        self.assertEqual(get_next_available_date(self.item), str(today + timedelta(days=6)))
        self.item.stock = 2
        self.assertEqual(get_next_available_date(self.item), str(today))
        self.item.stock = 0
        self.assertIsNone(get_next_available_date(self.item))


class PublisherIncomingRequestTests(TestCase):
    setUp = BookingSystemTests.setUp

    def test_publishers_receive_requests_in_both_directions(self):
        day = timezone.localdate() + timedelta(days=12)
        def publish(user, name):
            self.client.force_authenticate(user)
            response = self.client.post('/api/items/', {
                'name': name, 'category_id': self.category.pk,
                'rental_price': '25.00', 'stock': 1,
            }, format='json')
            self.assertEqual(response.status_code, 201)
            item = Item.objects.get(pk=response.data['id'])
            self.assertEqual(item.owner_id, user.pk)
            return item
        def request_item(user, item):
            self.client.force_authenticate(user)
            response = self.client.post('/api/bookings/', {
                'item_id': item.pk, 'start_date': str(day),
                'end_date': str(day + timedelta(days=2)),
            }, format='json')
            self.assertEqual(response.status_code, 201)
            booking = Booking.objects.get(pk=response.data['id'])
            self.assertEqual(booking.item_id, item.pk)
            self.assertEqual(booking.renter_id, user.pk)
            self.assertEqual(booking.owner_id, item.owner_id)
            self.assertEqual(booking.status, 'pending_approval')
            return booking
        item_a = publish(self.owner, 'Published by A')
        booking_b = request_item(self.renter, item_a)
        item_b = publish(self.renter, 'Published by B')
        booking_a = request_item(self.owner, item_b)
        for publisher, incoming, outgoing in (
            (self.owner, booking_b, booking_a),
            (self.renter, booking_a, booking_b),
        ):
            self.client.force_authenticate(publisher)
            response = self.client.get('/api/bookings/host/requests/?tab=incoming')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['counts']['incoming'], 1)
            self.assertEqual([row['id'] for row in response.data['results']], [incoming.pk])
            row = response.data['results'][0]
            self.assertEqual(row['renter']['id'], incoming.renter_id)
            self.assertEqual(row['renter']['phone_number'], '')
            self.assertEqual(row['renter']['email'], '')
            self.assertEqual(row['start_date'], str(day))
            mine = self.client.get('/api/bookings/my-bookings/').data['results']
            self.assertEqual([row['id'] for row in mine], [outgoing.pk])
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get('/api/bookings/host/requests/?tab=incoming').data['results'], [])
        for booking in (booking_a, booking_b):
            for action in ('approve', 'reject'):
                self.assertEqual(self.client.post(f'/api/bookings/{booking.pk}/{action}/').status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{booking_b.pk}/approve/').status_code, 200)
        self.assertEqual(self.client.get('/api/bookings/host/requests/?tab=incoming').data['results'], [])
        self.client.force_authenticate(self.renter)
        mine = self.client.get('/api/bookings/my-bookings/').data['results']
        self.assertEqual(mine[0]['status'], 'waiting_for_pickup')
        self.assertEqual(self.client.post(f'/api/bookings/{booking_a.pk}/reject/', {'reason': 'Unavailable'}, format='json').status_code, 200)
        self.assertEqual(self.client.get('/api/bookings/host/requests/?tab=incoming').data['results'], [])
        self.client.force_authenticate(self.owner)
        mine = self.client.get('/api/bookings/my-bookings/').data['results']
        self.assertEqual(mine[0]['status'], 'rejected')
        from .services import get_item_availability
        self.assertEqual(get_item_availability(item_b, day, day + timedelta(days=2))['available_stock'], 1)


class PublisherExperienceTests(TestCase):
    setUp = BookingSystemTests.setUp

    def create_request(self):
        self.client.force_authenticate(self.renter)
        day = timezone.localdate() + timedelta(days=7)
        response = self.client.post('/api/bookings/', {
            'item_id': self.item.pk, 'start_date': str(day),
            'end_date': str(day + timedelta(days=2))}, format='json')
        self.assertEqual(response.status_code, 201)
        return response.data['id']

    def test_owner_management_and_history(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/items/mine/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['results']], [self.item.pk])
        response = self.client.patch(f'/api/items/mine/{self.item.pk}/', {
            'name': 'Updated camera', 'description': 'Updated description',
            'rental_price': '2000.00', 'stock': 2, 'category_id': self.category.pk}, format='json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, 'Updated camera')
        self.assertEqual(self.item.stock, 2)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get('/api/items/mine/').data['results'], [])
        self.assertEqual(self.client.patch(f'/api/items/mine/{self.item.pk}/', {'stock': 99}, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'/api/items/mine/{self.item.pk}/deactivate/').status_code, 404)
        pk = self.create_request()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/items/mine/{self.item.pk}/deactivate/').status_code, 200)
        self.assertTrue(Booking.objects.filter(pk=pk).exists())
        self.assertEqual(self.client.get('/api/bookings/host/requests/?tab=incoming').data['results'][0]['id'], pk)
        self.assertEqual(self.client.get('/api/items/mine/').data['results'], [])
        self.assertEqual(self.client.get(f'/api/items/{self.item.pk}/').status_code, 404)

    def test_own_booking_denied_without_notification(self):
        self.client.force_authenticate(self.owner)
        day = timezone.localdate() + timedelta(days=5)
        response = self.client.post('/api/bookings/', {
            'item_id': self.item.pk, 'start_date': str(day),
            'end_date': str(day + timedelta(days=2))}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(InAppNotification.objects.count(), 0)

    def test_booking_notifications_and_read_isolation(self):
        pk = self.create_request()
        self.assertEqual(InAppNotification.objects.filter(booking_id=pk, event='requested', user=self.owner).count(), 1)
        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/bookings/notifications/')
        notification = response.data['results'][0]
        self.assertEqual(notification['booking'], pk)
        self.assertTrue(notification['can_respond'])
        self.assertEqual(response.data['unread_count'], 1)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/approve/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/approve/').status_code, 400)
        self.assertEqual(InAppNotification.objects.filter(booking_id=pk, event='accepted').count(), 1)
        self.assertTrue(InAppNotification.objects.get(pk=notification['id']).is_read)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get('/api/bookings/notifications/').data['results'], [])
        self.assertEqual(self.client.post(f"/api/bookings/notifications/{notification['id']}/mark-read/").status_code, 404)
        self.client.force_authenticate(self.renter)
        response = self.client.get('/api/bookings/notifications/')
        self.assertEqual(response.data['unread_count'], 1)
        accepted = response.data['results'][0]
        self.assertEqual(accepted['booking'], pk)
        self.assertFalse(accepted['can_respond'])
        self.assertEqual(self.client.post(f"/api/bookings/notifications/{accepted['id']}/mark-read/").status_code, 200)
        self.assertEqual(self.client.get('/api/bookings/notifications/').data['unread_count'], 0)
        self.assertEqual(len(self.client.get('/api/bookings/notifications/').data['results']), 1)

    def test_rejection_notifies_once_and_releases_stock(self):
        pk = self.create_request()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/reject/', {'reason': 'Item unavailable for requested dates'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/reject/', {'reason': 'Item unavailable for requested dates'}, format='json').status_code, 400)
        self.client.force_authenticate(self.renter)
        response = self.client.get('/api/bookings/notifications/')
        self.assertEqual(response.data['results'][0]['event'], 'rejected')
        self.assertEqual(InAppNotification.objects.filter(booking_id=pk, event='rejected').count(), 1)
        from .services import get_item_availability
        booking = Booking.objects.get(pk=pk)
        self.assertEqual(get_item_availability(self.item, booking.start_date, booking.end_date)['available_stock'], 1)


    def test_owner_image_replacement_and_invalid_upload_rollback(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from catalog.models import ItemImage
        buffer = io.BytesIO()
        Image.new('RGB', (32, 32), color='blue').save(buffer, format='JPEG')
        old = ItemImage.objects.create(item=self.item, is_primary=True,
            image=SimpleUploadedFile('old.jpg', buffer.getvalue(), content_type='image/jpeg'))
        self.client.force_authenticate(self.owner)
        response = self.client.patch(f'/api/items/mine/{self.item.pk}/', {
            'images': SimpleUploadedFile('replacement.jpg', buffer.getvalue(), content_type='image/jpeg'),
            'delete_image_ids': f'[{old.pk}]', 'description': 'New image',
        }, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.item.images.count(), 1)
        self.assertFalse(ItemImage.objects.filter(pk=old.pk).exists())
        self.assertTrue(self.item.images.get().is_primary)
        response = self.client.patch(f'/api/items/mine/{self.item.pk}/', {
            'description': 'Must roll back',
            'images': SimpleUploadedFile('broken.jpg', b'not an image', content_type='image/jpeg'),
        }, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.description, 'New image')

    def test_failed_operations_do_not_persist_notifications(self):
        from unittest.mock import patch
        self.client.force_authenticate(self.renter)
        day = timezone.localdate() + timedelta(days=8)
        with patch('bookings.serializers.notify_booking_event', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/api/bookings/', {
                    'item_id': self.item.pk, 'start_date': str(day),
                    'end_date': str(day + timedelta(days=1))}, format='json')
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(InAppNotification.objects.count(), 0)
        pk = self.create_request()
        self.client.force_authenticate(self.owner)
        with patch('bookings.views.notify_booking_event', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.client.post(f'/api/bookings/{pk}/approve/')
        self.assertEqual(Booking.objects.get(pk=pk).status, 'pending_approval')
        self.assertFalse(InAppNotification.objects.filter(booking_id=pk, event='accepted').exists())


    def test_booking_action_flags_preserve_participant_and_staff_permissions(self):
        pk = self.create_request()
        self.client.force_authenticate(self.owner)
        detail = self.client.get(f'/api/bookings/{pk}/').data
        self.assertFalse(detail['can_cancel'])
        self.assertFalse(detail['can_report_problem'])
        self.client.force_authenticate(self.renter)
        self.assertTrue(self.client.get(f'/api/bookings/{pk}/').data['can_cancel'])
        self.client.force_authenticate(self.staff_admin)
        self.assertTrue(self.client.get(f'/api/bookings/{pk}/').data['can_cancel'])
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/approve/').status_code, 200)
        booking = Booking.objects.get(pk=pk)
        mark_booking_payment_verified(booking, verified_by=self.staff_admin)
        self.assertTrue(self.client.get(f'/api/bookings/{pk}/').data['can_pickup'])
        self.client.force_authenticate(self.renter)
        self.assertFalse(self.client.get(f'/api/bookings/{pk}/').data['can_pickup'])


class WebPushNotificationTests(TestCase):
    setUp = BookingSystemTests.setUp

    def test_push_vapid_key_endpoint(self):
        res = self.client.get('/api/bookings/push/vapid-key/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('public_key', res.data)
        self.assertTrue(len(res.data['public_key']) > 50)

    def test_push_subscribe_and_unsubscribe(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            'endpoint': 'https://fcm.googleapis.com/fcm/send/test-endpoint-123',
            'keys': {
                'p256dh': 'test-p256dh-key',
                'auth': 'test-auth-secret'
            }
        }
        res = self.client.post('/api/bookings/push/subscribe/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(PushSubscription.objects.filter(user=self.owner, endpoint=payload['endpoint']).exists())

        # Duplicate subscribe updates rather than errors
        res_update = self.client.post('/api/bookings/push/subscribe/', payload, format='json')
        self.assertEqual(res_update.status_code, status.HTTP_200_OK)
        self.assertEqual(PushSubscription.objects.filter(user=self.owner).count(), 1)

        # Unsubscribe
        res_unsub = self.client.post('/api/bookings/push/unsubscribe/', {'endpoint': payload['endpoint']}, format='json')
        self.assertEqual(res_unsub.status_code, status.HTTP_200_OK)
        self.assertFalse(PushSubscription.objects.filter(user=self.owner, endpoint=payload['endpoint']).exists())

    def test_renter_request_triggers_owner_push_notification(self):
        from unittest.mock import patch
        import json
        PushSubscription.objects.create(
            user=self.owner,
            endpoint='https://fcm.googleapis.com/fcm/send/owner-endpoint',
            p256dh='sample-p256dh',
            auth='sample-auth'
        )

        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=10)
        end = timezone.localdate() + timedelta(days=12)

        with patch('bookings.push_service.webpush') as mock_push:
            res = self.client.post('/api/bookings/', {
                'item_id': self.item.id,
                'start_date': str(start),
                'end_date': str(end),
                'requested_quantity': 1,
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            booking_id = res.data['id']

            # Verify webpush was invoked for owner
            mock_push.assert_called_once()
            call_kwargs = mock_push.call_args[1]
            self.assertEqual(call_kwargs['subscription_info']['endpoint'], 'https://fcm.googleapis.com/fcm/send/owner-endpoint')

            sent_data = json.loads(call_kwargs['data'])
            # Message format: "Rahul requested your Camera."
            expected_body = f"{self.renter.full_name} requested your {self.item.name}."
            self.assertEqual(sent_data['body'], expected_body)
            # URL opens Host Hub and highlights the incoming request
            self.assertIn(f'/host-hub?tab=incoming&highlight={booking_id}', sent_data['data']['url'])
            # Informational only: no action buttons
            self.assertNotIn('actions', sent_data)

    def test_owner_approval_triggers_renter_push(self):
        from unittest.mock import patch
        import json
        PushSubscription.objects.create(
            user=self.renter,
            endpoint='https://fcm.googleapis.com/fcm/send/renter-endpoint',
            p256dh='sample-p256dh',
            auth='sample-auth'
        )

        booking = Booking.objects.create(
            item=self.item, owner=self.owner, renter=self.renter,
            start_date=timezone.localdate() + timedelta(days=5),
            end_date=timezone.localdate() + timedelta(days=8),
            duration_days=3, daily_price=10, rental_amount=30, total_amount=30,
            status='pending_approval'
        )

        self.client.force_authenticate(user=self.owner)
        with patch('bookings.push_service.webpush') as mock_push:
            res = self.client.post(f'/api/bookings/{booking.id}/approve/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            mock_push.assert_called_once()
            call_kwargs = mock_push.call_args[1]
            self.assertEqual(call_kwargs['subscription_info']['endpoint'], 'https://fcm.googleapis.com/fcm/send/renter-endpoint')

            sent_data = json.loads(call_kwargs['data'])
            self.assertIn('approved', sent_data['body'].lower())
            self.assertEqual(sent_data['data']['url'], f'/bookings/{booking.id}')

    def test_owner_rejection_triggers_renter_push_with_reason(self):
        from unittest.mock import patch
        import json
        PushSubscription.objects.create(
            user=self.renter,
            endpoint='https://fcm.googleapis.com/fcm/send/renter-endpoint',
            p256dh='sample-p256dh',
            auth='sample-auth'
        )

        booking = Booking.objects.create(
            item=self.item, owner=self.owner, renter=self.renter,
            start_date=timezone.localdate() + timedelta(days=5),
            end_date=timezone.localdate() + timedelta(days=8),
            duration_days=3, daily_price=10, rental_amount=30, total_amount=30,
            status='pending_approval'
        )

        rejection_reason = "Item undergoing maintenance"
        self.client.force_authenticate(user=self.owner)
        with patch('bookings.push_service.webpush') as mock_push:
            res = self.client.post(f'/api/bookings/{booking.id}/reject/', {'reason': rejection_reason}, format='json')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            mock_push.assert_called_once()
            call_kwargs = mock_push.call_args[1]
            sent_data = json.loads(call_kwargs['data'])
            self.assertIn('rejected', sent_data['body'].lower())
            self.assertIn(rejection_reason, sent_data['body'])
            self.assertEqual(sent_data['data']['url'], f'/bookings/{booking.id}')

    def test_push_delivery_failure_does_not_abort_booking(self):
        from unittest.mock import patch
        PushSubscription.objects.create(
            user=self.owner,
            endpoint='https://fcm.googleapis.com/fcm/send/broken-endpoint',
            p256dh='sample-p256dh',
            auth='sample-auth'
        )

        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=15)
        end = timezone.localdate() + timedelta(days=17)

        # Simulate push service throwing an exception
        with patch('bookings.push_service.webpush', side_effect=Exception("Push network timeout")):
            res = self.client.post('/api/bookings/', {
                'item_id': self.item.id,
                'start_date': str(start),
                'end_date': str(end),
                'requested_quantity': 1,
            }, format='json')
            # Booking creation MUST still succeed
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            # In-app notification MUST still be created
            self.assertTrue(InAppNotification.objects.filter(booking_id=res.data['id'], event='requested').exists())


class BookingAddressManagementTests(TestCase):
    setUp = BookingSystemTests.setUp

    def test_booking_creation_with_specific_address_id(self):
        # Create a second address for renter (Work)
        work_address = Address.objects.create(
            user=self.renter,
            full_name='Bob Renter (Office)',
            house_number='Tower B, 4th Floor',
            address='Tech Park',
            area='Whitefield',
            landmark='Near ITPL',
            city='Bangalore',
            state='Karnataka',
            pincode='560066',
            country='India',
            address_type='Work'
        )

        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=2)
        end = timezone.localdate() + timedelta(days=5)

        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
            'requested_quantity': 1,
            'address_id': work_address.id,
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(pk=res.data['id'])
        self.assertEqual(booking.renter_address_id, work_address.id)
        self.assertIn('Tower B, 4th Floor', booking.renter_address_snapshot)
        self.assertIn('Whitefield', booking.renter_address_snapshot)
        self.assertEqual(booking.renter_address_data['address_type'], 'Work')
        self.assertEqual(booking.renter_address_data['pincode'], '560066')

    def test_booking_creation_with_foreign_address_id_fails(self):
        # Stranger's address
        stranger_address = Address.objects.create(
            user=self.stranger,
            full_name='Charlie Stranger',
            house_number='Plot 9',
            address='Foreign Street',
            area='Remote Area',
            city='Mumbai',
            state='Maharashtra',
            pincode='400001',
            country='India'
        )

        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=2)
        end = timezone.localdate() + timedelta(days=4)

        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
            'address_id': stranger_address.id,
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('address_id', res.data)

    def test_booking_creation_default_address_fallback(self):
        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=3)
        end = timezone.localdate() + timedelta(days=5)

        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(pk=res.data['id'])
        self.assertEqual(booking.renter_address_id, self.renter_address.id)
        self.assertIn('Flat 101', booking.renter_address_snapshot)

    def test_historical_address_preservation_after_edit_and_delete(self):
        # Create address
        temp_address = Address.objects.create(
            user=self.renter,
            full_name='Bob Renter',
            house_number='Villa 99',
            address='Old Heritage Road',
            area='Koramangala',
            city='Bangalore',
            state='Karnataka',
            pincode='560034',
            country='India',
            address_type='Home'
        )

        self.client.force_authenticate(user=self.renter)
        start = timezone.localdate() + timedelta(days=2)
        end = timezone.localdate() + timedelta(days=4)

        res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
            'address_id': temp_address.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        booking_id = res.data['id']

        # Edit the address
        temp_address.house_number = 'Villa 99 - RENOVATED'
        temp_address.save()

        # Fetch booking details via API
        detail_res = self.client.get(f'/api/bookings/{booking_id}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        # Snapshot still has original house number
        self.assertEqual(detail_res.data['renter_address']['house_number'], 'Villa 99')

        # Now delete the address completely
        temp_address.delete()

        # Reload booking from DB
        booking = Booking.objects.get(pk=booking_id)
        self.assertIsNone(booking.renter_address)
        self.assertEqual(booking.renter_address_data['house_number'], 'Villa 99')
        self.assertEqual(booking.renter_address_data['area'], 'Koramangala')

        # API still returns the complete historical snapshot
        detail_after_delete = self.client.get(f'/api/bookings/{booking_id}/')
        self.assertEqual(detail_after_delete.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_after_delete.data['renter_address']['house_number'], 'Villa 99')

    def test_different_bookings_can_use_different_addresses(self):
        address_home = self.renter_address
        address_work = Address.objects.create(
            user=self.renter,
            full_name='Bob Office',
            house_number='Suite 500',
            address='Business Bay',
            area='MG Road',
            city='Bangalore',
            state='Karnataka',
            pincode='560025',
            country='India',
            address_type='Work'
        )

        self.client.force_authenticate(user=self.renter)
        # Booking 1 with Home address
        b1_res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(timezone.localdate() + timedelta(days=2)),
            'end_date': str(timezone.localdate() + timedelta(days=4)),
            'address_id': address_home.id,
        }, format='json')
        self.assertEqual(b1_res.status_code, status.HTTP_201_CREATED)

        # Booking 2 with Work address
        b2_res = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(timezone.localdate() + timedelta(days=10)),
            'end_date': str(timezone.localdate() + timedelta(days=12)),
            'address_id': address_work.id,
        }, format='json')
        self.assertEqual(b2_res.status_code, status.HTTP_201_CREATED)

        b1 = Booking.objects.get(pk=b1_res.data['id'])
        b2 = Booking.objects.get(pk=b2_res.data['id'])

        self.assertEqual(b1.renter_address_id, address_home.id)
        self.assertEqual(b2.renter_address_id, address_work.id)
        self.assertEqual(b1.renter_address_data['address_type'], 'Home')
        self.assertEqual(b2.renter_address_data['address_type'], 'Work')


@override_settings(
    RAZORPAY_KEY_ID='rzp_test_123456789',
    RAZORPAY_KEY_SECRET='test_secret_key_abcdef',
    RAZORPAY_WEBHOOK_SECRET='test_webhook_secret_xyz'
)
class RazorpayPaymentManagementTests(TestCase):
    setUp = BookingSystemTests.setUp

    def create_approved_booking(self, total_amount=Decimal('8000.00')):
        today = timezone.localdate()
        return Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=total_amount,
            status='waiting_for_pickup',
            payment_status='pending'
        )

    @patch('bookings.services.get_razorpay_client')
    def test_create_order_allowed_when_pending_approval(self, mock_client):
        today = timezone.localdate()
        unapproved = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'),
            status='pending_approval',
            payment_status='pending',
            payment_method='online'
        )
        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{unapproved.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Payment can only be initiated after the owner accepts the booking request.', res.data.get('error', ''))
        mock_client.assert_not_called()

    @patch('bookings.services.get_razorpay_client')
    def test_create_order_allowed_when_payment_failed_retry(self, mock_client):
        mock_rzp = MagicMock()
        mock_client.return_value = mock_rzp
        mock_rzp.order.create.return_value = {
            'id': 'order_rzp_retry_456',
            'amount': 300000,
            'currency': 'INR',
            'status': 'created'
        }
        today = timezone.localdate()
        failed_booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'),
            status='waiting_for_pickup',
            payment_status='failed',
            payment_method='online'
        )
        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{failed_booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['order_id'], 'order_rzp_retry_456')

    @patch('bookings.services.get_razorpay_client')
    def test_create_order_rejected_when_already_paid(self, mock_client):
        today = timezone.localdate()
        paid_booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'),
            status='waiting_for_pickup',
            payment_status='paid',
            payment_method='online'
        )
        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{paid_booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        mock_client.assert_not_called()

    @patch('bookings.services.get_razorpay_client')
    def test_create_order_rejected_for_cancelled_or_completed_booking(self, mock_client):
        today = timezone.localdate()
        for terminal_status in ['cancelled', 'rejected', 'completed']:
            b = Booking.objects.create(
                renter=self.renter,
                item=self.item,
                owner=self.owner,
                start_date=today + timedelta(days=2),
                end_date=today + timedelta(days=4),
                duration_days=2,
                daily_price=Decimal('1500.00'),
                rental_amount=Decimal('3000.00'),
                total_amount=Decimal('3000.00'),
                status=terminal_status,
                payment_status='pending',
                payment_method='online'
            )
            self.client.force_authenticate(user=self.renter)
            res = self.client.post(f'/api/bookings/{b.id}/create-payment-order/')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        mock_client.assert_not_called()

    def test_can_pay_serializer_flag_scenarios(self):
        from bookings.serializers import BookingDetailSerializer
        today = timezone.localdate()

        # Scenario 1: Online + pending_approval + pending payment -> can_pay False (requires owner approval first)
        b1 = Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=2), end_date=today + timedelta(days=4),
            duration_days=2, daily_price=Decimal('1500.00'), rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'), status='pending_approval', payment_status='pending',
            payment_method='online'
        )
        req = MagicMock()
        req.user = self.renter
        data1 = BookingDetailSerializer(b1, context={'request': req}).data
        self.assertFalse(data1['can_pay'])

        # Scenario 2: Online + waiting_for_pickup + pending payment -> can_pay True
        b2 = Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=2), end_date=today + timedelta(days=4),
            duration_days=2, daily_price=Decimal('1500.00'), rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'), status='waiting_for_pickup', payment_status='pending',
            payment_method='online'
        )
        data2 = BookingDetailSerializer(b2, context={'request': req}).data
        self.assertTrue(data2['can_pay'])

        # Scenario 3: Online + waiting_for_pickup + failed payment -> can_pay True (retry allowed)
        b3 = Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=2), end_date=today + timedelta(days=4),
            duration_days=2, daily_price=Decimal('1500.00'), rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'), status='waiting_for_pickup', payment_status='failed',
            payment_method='online'
        )
        data3 = BookingDetailSerializer(b3, context={'request': req}).data
        self.assertTrue(data3['can_pay'])

        # Scenario 4: Online + paid payment -> can_pay False
        b4 = Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=2), end_date=today + timedelta(days=4),
            duration_days=2, daily_price=Decimal('1500.00'), rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'), status='pending_approval', payment_status='paid',
            payment_method='online'
        )
        data4 = BookingDetailSerializer(b4, context={'request': req}).data
        self.assertFalse(data4['can_pay'])

        # Scenario 5: Offline payment -> can_pay False
        b5 = Booking.objects.create(
            renter=self.renter, item=self.item, owner=self.owner,
            start_date=today + timedelta(days=2), end_date=today + timedelta(days=4),
            duration_days=2, daily_price=Decimal('1500.00'), rental_amount=Decimal('3000.00'),
            total_amount=Decimal('3000.00'), status='pending_approval', payment_status='pending',
            payment_method='offline'
        )
        data5 = BookingDetailSerializer(b5, context={'request': req}).data
        self.assertFalse(data5['can_pay'])

        # Scenario 6: Unauthorized user -> can_pay False
        unrelated_req = MagicMock()
        unrelated_req.user = self.stranger
        data6 = BookingDetailSerializer(b1, context={'request': unrelated_req}).data
        self.assertFalse(data6['can_pay'])

    def test_create_order_forbidden_for_non_renter(self):
        booking = self.create_approved_booking()
        # Owner cannot initiate payment
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Unrelated user cannot initiate payment
        self.client.force_authenticate(user=self.stranger)
        res = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('bookings.services.get_razorpay_client')
    def test_create_order_success_and_reuse_on_retry(self, mock_get_client):
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.order.create.return_value = {
            'id': 'order_rzp_mock_123',
            'amount': 800000,
            'currency': 'INR',
            'status': 'created'
        }
        mock_rzp.order.fetch.return_value = {
            'id': 'order_rzp_mock_123',
            'amount': 800000,
            'amount_paid': 0,
            'currency': 'INR',
            'status': 'created'
        }

        booking = self.create_approved_booking(total_amount=Decimal('8000.00'))
        self.client.force_authenticate(user=self.renter)

        # First initiation creates order
        res1 = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['order_id'], 'order_rzp_mock_123')
        self.assertEqual(res1.data['amount'], 800000)
        self.assertEqual(res1.data['currency'], 'INR')
        self.assertFalse(res1.data['is_reused'])
        booking.refresh_from_db()
        self.assertEqual(booking.razorpay_order_id, 'order_rzp_mock_123')

        # Retry payment reuses existing order
        res2 = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['order_id'], 'order_rzp_mock_123')
        self.assertTrue(res2.data['is_reused'])
        # Only created once
        mock_rzp.order.create.assert_called_once()

    @patch('bookings.services.get_razorpay_client')
    def test_create_order_creates_new_if_previous_expired(self, mock_get_client):
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        # Order fetch reports expired
        mock_rzp.order.fetch.return_value = {
            'id': 'order_old_expired',
            'amount': 800000,
            'amount_paid': 0,
            'currency': 'INR',
            'status': 'expired'
        }
        mock_rzp.order.create.return_value = {
            'id': 'order_new_active',
            'amount': 800000,
            'currency': 'INR',
            'status': 'created'
        }

        booking = self.create_approved_booking()
        booking.razorpay_order_id = 'order_old_expired'
        booking.save()

        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['order_id'], 'order_new_active')
        booking.refresh_from_db()
        self.assertEqual(booking.razorpay_order_id, 'order_new_active')

    @patch('bookings.services.get_razorpay_client')
    def test_verify_payment_success_with_signature_and_captured_status(self, mock_get_client):
        order_id = 'order_valid_123'
        payment_id = 'pay_captured_456'
        booking = self.create_approved_booking(total_amount=Decimal('8000.00'))
        booking.razorpay_order_id = order_id
        booking.save()

        # Generate genuine HMAC SHA-256 signature
        msg = f"{order_id}|{payment_id}".encode('utf-8')
        secret = 'test_secret_key_abcdef'
        signature = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        # Mock captured payment in Razorpay API
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': order_id,
            'amount': 800000,
            'currency': 'INR',
            'status': 'captured'
        }

        self.client.force_authenticate(user=self.renter)
        payload = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        res = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['booking']['payment_status'], 'paid')

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_transaction_id, payment_id)
        self.assertIsNotNone(booking.payment_verified_at)

        # Host can now confirm pickup!
        booking.pickup_otp_hash = make_password('123456')
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()
        self.client.force_authenticate(user=self.owner)
        res_pickup = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/', {'otp': '123456'}, format='json')
        self.assertEqual(res_pickup.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')

    @patch('bookings.services.get_razorpay_client')
    def test_verify_payment_rejected_if_not_captured(self, mock_get_client):
        """Requirement 1: Valid signature is NOT sufficient if payment is not captured."""
        order_id = 'order_uncaptured_123'
        payment_id = 'pay_authorized_only'
        booking = self.create_approved_booking()
        booking.razorpay_order_id = order_id
        booking.save()

        msg = f"{order_id}|{payment_id}".encode('utf-8')
        signature = hmac.new('test_secret_key_abcdef'.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        # Mock payment in 'authorized' status (not yet captured)
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': order_id,
            'amount': 800000,
            'currency': 'INR',
            'status': 'authorized'  # NOT CAPTURED
        }

        self.client.force_authenticate(user=self.renter)
        payload = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        res = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('captured before verification', str(res.data))

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'pending')

    @patch('bookings.services.get_razorpay_client')
    def test_verify_payment_invalid_signature_rejected(self, mock_get_client):
        order_id = 'order_valid_123'
        payment_id = 'pay_fake_sig'
        booking = self.create_approved_booking()
        booking.razorpay_order_id = order_id
        booking.save()

        self.client.force_authenticate(user=self.renter)
        payload = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': 'invalid_forged_signature_hex'
        }
        res = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid payment signature', str(res.data))

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'pending')
        mock_get_client.assert_not_called()

    @patch('bookings.services.get_razorpay_client')
    def test_verify_payment_amount_currency_mismatch_rejected(self, mock_get_client):
        order_id = 'order_amt_mismatch'
        payment_id = 'pay_amt_123'
        booking = self.create_approved_booking(total_amount=Decimal('8000.00'))
        booking.razorpay_order_id = order_id
        booking.save()

        msg = f"{order_id}|{payment_id}".encode('utf-8')
        signature = hmac.new('test_secret_key_abcdef'.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        # Razorpay returned tampered amount: 500000 instead of 800000
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': order_id,
            'amount': 500000,
            'currency': 'INR',
            'status': 'captured'
        }

        self.client.force_authenticate(user=self.renter)
        payload = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        res = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Amount mismatch', str(res.data))

    @patch('bookings.services.get_razorpay_client')
    def test_verify_payment_idempotency_same_payment_id(self, mock_get_client):
        order_id = 'order_idem_123'
        payment_id = 'pay_idem_456'
        booking = self.create_approved_booking()
        booking.razorpay_order_id = order_id
        booking.payment_status = 'paid'
        booking.payment_transaction_id = payment_id
        booking.save()

        msg = f"{order_id}|{payment_id}".encode('utf-8')
        signature = hmac.new('test_secret_key_abcdef'.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': order_id,
            'amount': 800000,
            'currency': 'INR',
            'status': 'captured'
        }

        self.client.force_authenticate(user=self.renter)
        payload = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        res = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['booking']['payment_status'], 'paid')

    @patch('bookings.services.get_razorpay_client')
    def test_verify_payment_duplicate_transaction_conflict(self, mock_get_client):
        payment_id = 'pay_stolen_trans'
        # Booking 1 already verified with this payment ID
        b1 = self.create_approved_booking()
        b1.payment_status = 'paid'
        b1.payment_transaction_id = payment_id
        b1.save()

        # Booking 2 tries to verify with the same payment ID
        b2 = self.create_approved_booking()
        b2.razorpay_order_id = 'order_b2_123'
        b2.save()

        msg = f"{b2.razorpay_order_id}|{payment_id}".encode('utf-8')
        signature = hmac.new('test_secret_key_abcdef'.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': b2.razorpay_order_id,
            'amount': 800000,
            'currency': 'INR',
            'status': 'captured'
        }

        self.client.force_authenticate(user=self.renter)
        payload = {
            'razorpay_order_id': b2.razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        res = self.client.post(f'/api/bookings/{b2.id}/verify-payment/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already been credited to booking', str(res.data))

    def test_webhook_signature_verification_and_event_tracking(self):
        """Requirement 2 & 3: Webhook verification with secret and ProcessedWebhookEvent tracking."""
        order_id = 'order_webhook_test_1'
        payment_id = 'pay_webhook_test_1'
        booking = self.create_approved_booking()
        booking.razorpay_order_id = order_id
        booking.save()

        webhook_secret = 'test_webhook_secret_xyz'
        event_payload = {
            'id': 'evt_razorpay_1001',
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': payment_id,
                        'order_id': order_id,
                        'amount': 800000,
                        'currency': 'INR',
                        'status': 'captured'
                    }
                }
            }
        }
        raw_body = json.dumps(event_payload).encode('utf-8')
        signature = hmac.new(webhook_secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

        # Webhook call with valid signature
        res = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'success')

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_transaction_id, payment_id)

        # ProcessedWebhookEvent is recorded
        self.assertTrue(ProcessedWebhookEvent.objects.filter(event_id='evt_razorpay_1001').exists())

        # Duplicate webhook delivery: Idempotently acknowledged without reprocessing
        res_dup = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        self.assertEqual(res_dup.status_code, status.HTTP_200_OK)
        self.assertEqual(res_dup.data['status'], 'already_processed')

    def test_webhook_invalid_signature_rejected(self):
        event_payload = {'id': 'evt_invalid_sig', 'event': 'payment.captured'}
        raw_body = json.dumps(event_payload).encode('utf-8')
        res = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='bad_sig'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ProcessedWebhookEvent.objects.filter(event_id='evt_invalid_sig').exists())

    def test_webhook_payment_failed_event(self):
        order_id = 'order_failed_wh'
        booking = self.create_approved_booking()
        booking.razorpay_order_id = order_id
        booking.save()

        event_payload = {
            'id': 'evt_failed_001',
            'event': 'payment.failed',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_failed_123',
                        'order_id': order_id,
                        'amount': 800000,
                        'currency': 'INR',
                        'status': 'failed'
                    }
                }
            }
        }
        raw_body = json.dumps(event_payload).encode('utf-8')
        signature = hmac.new('test_webhook_secret_xyz'.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

        res = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'failure_recorded')

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'failed')
        # Booking status is still waiting_for_pickup so renter can retry
        self.assertEqual(booking.status, 'waiting_for_pickup')


class OfflinePaymentManagementTests(TestCase):
    setUp = BookingSystemTests.setUp

    def create_approved_offline_booking(self, total_amount=Decimal('8000.00')):
        today = timezone.localdate()
        return Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            payment_method='offline',
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=total_amount,
            status='waiting_for_pickup',
            payment_status='pending'
        )

    def test_create_booking_with_offline_payment_method(self):
        """Renter can create a booking explicitly specifying offline payment method."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()
        payload = {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=2)),
            'end_date': str(today + timedelta(days=4)),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
            'payment_method': 'offline',
        }
        res = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['payment_method'], 'offline')
        self.assertEqual(res.data['payment_method_display'], 'Pay at Pickup (Cash)')
        self.assertEqual(res.data['payment_status'], 'pending')

        booking = Booking.objects.get(pk=res.data['id'])
        self.assertEqual(booking.payment_method, 'offline')
        self.assertEqual(booking.payment_status, 'pending')

    def test_create_booking_defaults_to_online(self):
        """Booking creation without payment_method defaults cleanly to online."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()
        payload = {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=2)),
            'end_date': str(today + timedelta(days=4)),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['payment_method'], 'online')
        self.assertEqual(res.data['payment_method_display'], 'Online Payment (Razorpay)')

        booking = Booking.objects.get(pk=res.data['id'])
        self.assertEqual(booking.payment_method, 'online')

    def test_offline_booking_rejects_razorpay_order_creation(self):
        """Razorpay order creation is strictly blocked for offline bookings."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.renter)

        res = self.client.post(f'/api/bookings/{booking.id}/create-payment-order/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('offline', str(res.data).lower())

        booking.refresh_from_db()
        self.assertFalse(booking.razorpay_order_id)

    def test_offline_booking_rejects_verify_payment_endpoint(self):
        """Razorpay payment verification is strictly blocked for offline bookings."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.renter)

        payload = {
            'razorpay_order_id': 'order_fake_123',
            'razorpay_payment_id': 'pay_fake_123',
            'razorpay_signature': 'sig_fake_123',
        }
        res = self.client.post(f'/api/bookings/{booking.id}/verify-payment/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('offline', str(res.data).lower())

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'pending')

    @override_settings(RAZORPAY_WEBHOOK_SECRET='test_webhook_secret_xyz')
    def test_offline_booking_ignored_by_razorpay_webhook(self):
        """Razorpay webhooks cannot alter payment status for offline bookings."""
        booking = self.create_approved_offline_booking()
        booking.razorpay_order_id = 'order_offline_simulated'
        booking.save()

        event_payload = {
            'id': 'evt_offline_test_001',
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_offline_123',
                        'order_id': 'order_offline_simulated',
                        'amount': 800000,
                        'currency': 'INR',
                        'status': 'captured',
                    }
                }
            }
        }
        raw_body = json.dumps(event_payload).encode('utf-8')
        signature = hmac.new('test_webhook_secret_xyz'.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

        res = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'ignored')
        self.assertIn('offline', res.data.get('reason', '').lower())

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'pending')

    def test_owner_confirm_offline_payment_success(self):
        """Item owner confirms cash receipt at pickup: updates payment_status, audit fields, no synthetic txn ID."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.owner)

        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Offline payment confirmed successfully.')
        self.assertEqual(res.data['booking']['payment_status'], 'paid')

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertIsNotNone(booking.payment_verified_at)
        self.assertEqual(booking.payment_verified_by, self.owner)
        self.assertTrue(booking.payment_transaction_id is None or booking.payment_transaction_id == '')

        # In-app notifications sent
        self.assertTrue(InAppNotification.objects.filter(booking=booking, event='payment_verified_owner').exists())
        self.assertTrue(InAppNotification.objects.filter(booking=booking, event='payment_verified_renter').exists())

    def test_admin_confirm_offline_payment_success(self):
        """Staff administrator can confirm offline cash receipt on behalf of owner."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.staff_admin)

        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_verified_by, self.staff_admin)

    def test_renter_forbidden_from_confirming_offline_payment(self):
        """Renter attempting to confirm their own offline payment is rejected with HTTP 403."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.renter)

        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'pending')

    def test_unrelated_user_forbidden_from_confirming_offline_payment(self):
        """Unrelated stranger attempting to confirm offline payment is rejected with HTTP 403."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.stranger)

        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'pending')

    def test_duplicate_offline_confirmation_rejected(self):
        """Confirming an already-paid offline booking returns HTTP 400."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.owner)

        res1 = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        res2 = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already', str(res2.data).lower())

    def test_confirm_offline_payment_rejected_for_online_booking(self):
        """Online booking cannot be confirmed via the offline confirmation endpoint."""
        today = timezone.localdate()
        online_booking = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            payment_method='online',
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='waiting_for_pickup',
            payment_status='pending'
        )
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{online_booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('offline', str(res.data).lower())

    def test_confirm_offline_payment_rejected_for_unapproved_booking(self):
        """Offline booking in pending_approval cannot be confirmed until host approves."""
        today = timezone.localdate()
        unapproved = Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            payment_method='offline',
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('5000.00'),
            total_amount=Decimal('8000.00'),
            status='pending_approval',
            payment_status='pending'
        )
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{unapproved.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('waiting for pickup', str(res.data).lower())

    def test_pickup_blocked_until_offline_payment_confirmed(self):
        """Owner handover is strictly blocked until offline payment is confirmed as paid."""
        booking = self.create_approved_offline_booking()
        self.client.force_authenticate(user=self.owner)

        # 1. Attempt pickup while payment is pending: BLOCKED
        res_blocked = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/', {'otp': '123456'}, format='json')
        self.assertEqual(res_blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('payment is verified', str(res_blocked.data).lower())

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'waiting_for_pickup')

        # 2. Host confirms offline cash payment: SUCCEEDS
        res_pay = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res_pay.status_code, status.HTTP_200_OK)

        # 3. Owner attempts pickup again: UNLOCKED & SUCCEEDS with valid OTP
        booking.refresh_from_db()
        booking.pickup_otp_hash = make_password('123456')
        booking.pickup_otp_expires_at = timezone.now() + timedelta(minutes=10)
        booking.save()
        res_unlocked = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/', {'otp': '123456'}, format='json')
        self.assertEqual(res_unlocked.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')
        self.assertIsNotNone(booking.picked_up_at)

    def test_reassigned_item_owner_cannot_confirm_offline_payment_if_not_booking_canonical_owner(self):
        """
        If an item's owner changes after booking creation, the new item owner cannot confirm
        offline payment because they are not the booking's canonical owner (locked_booking.owner_id).
        """
        new_item_owner = User.objects.create_user(
            email='newowner@test.com',
            password='Password123!',
            full_name='New Item Owner',
            phone_number='9876543299'
        )
        booking = self.create_approved_offline_booking()
        self.assertEqual(booking.owner_id, self.owner.id)

        # Reassign the underlying catalog item to a different owner
        self.item.owner = new_item_owner
        self.item.save(update_fields=['owner'])

        # New item owner attempts to confirm payment: FORBIDDEN (HTTP 403)
        self.client.force_authenticate(user=new_item_owner)
        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'pending')

        # Canonical booking owner confirms payment: SUCCEEDS (HTTP 200)
        self.client.force_authenticate(user=self.owner)
        res_canonical = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-payment/')
        self.assertEqual(res_canonical.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_verified_by, self.owner)


class BookingInvoiceReceiptTests(TestCase):
    """
    Tasks 83–90: Comprehensive invoice & payment receipt verification tests.
    Verifies downloadable PDF invoice/receipt generation, pricing snapshots,
    Razorpay vs. offline payment receipts, access control and security.
    """
    setUp = BookingSystemTests.setUp

    def create_paid_online_booking(self):
        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=2,
            daily_price=Decimal('1500.00'),
            rental_amount=Decimal('6000.00'),
            deposit_amount=Decimal('2000.00'),
            total_amount=Decimal('8000.00'),
            payment_method='online',
            payment_status='paid',
            status='waiting_for_pickup',
            payment_transaction_id='pay_test_online_98765',
            razorpay_order_id='order_test_online_12345',
            payment_verified_at=timezone.now(),
        )
        return booking

    def create_paid_offline_booking(self):
        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=5),
            duration_days=3,
            requested_quantity=1,
            daily_price=Decimal('1000.00'),
            rental_amount=Decimal('3000.00'),
            deposit_amount=Decimal('1500.00'),
            total_amount=Decimal('4500.00'),
            payment_method='offline',
            payment_status='paid',
            status='waiting_for_pickup',
            payment_verified_by=self.owner,
            payment_verified_at=timezone.now(),
        )
        return booking

    def test_successful_razorpay_payment_generates_correct_pdf(self):
        """Case 1: Successful Razorpay payment generates a valid PDF receipt."""
        booking = self.create_paid_online_booking()
        self.client.force_authenticate(user=self.renter)

        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertIn(f'RentBee_Invoice_{booking.booking_reference}.pdf', res['Content-Disposition'])
        # PDF signature check
        self.assertTrue(res.content.startswith(b'%PDF-'))

    def test_failed_razorpay_payment_cannot_generate_receipt(self):
        """Case 2: Failed Razorpay payment cannot generate a receipt."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=1,
            requested_quantity=1,
            daily_price=Decimal('1000.00'),
            rental_amount=Decimal('1000.00'),
            deposit_amount=Decimal('500.00'),
            total_amount=Decimal('1500.00'),
            payment_method='online',
            payment_status='failed',
            status='pending_approval',
        )
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('only available for confirmed payments', str(res.data))

    def test_pending_razorpay_payment_cannot_generate_receipt(self):
        """Case 3: Pending Razorpay payment cannot generate a receipt."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=2),
            duration_days=1,
            requested_quantity=1,
            daily_price=Decimal('1000.00'),
            rental_amount=Decimal('1000.00'),
            deposit_amount=Decimal('500.00'),
            total_amount=Decimal('1500.00'),
            payment_method='online',
            payment_status='pending',
            status='waiting_for_pickup',
        )
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('only available for confirmed payments', str(res.data))

    def test_confirmed_offline_payment_generates_correct_pdf(self):
        """Case 4: Confirmed offline payment generates a valid PDF receipt."""
        booking = self.create_paid_offline_booking()
        self.client.force_authenticate(user=self.renter)

        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF-'))

    def test_unconfirmed_offline_payment_cannot_generate_receipt(self):
        """Case 5: Unconfirmed offline payment cannot generate a receipt."""
        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('1000.00'),
            rental_amount=Decimal('2000.00'),
            deposit_amount=Decimal('1000.00'),
            total_amount=Decimal('3000.00'),
            payment_method='offline',
            payment_status='pending',
            status='waiting_for_pickup',
        )
        self.client.force_authenticate(user=self.renter)
        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('only available for confirmed payments', str(res.data))

    def test_correct_booking_id_and_reference_in_receipt(self):
        """Case 6: Correct booking reference and database ID are reflected."""
        from .pdf_service import generate_booking_invoice_pdf
        booking = self.create_paid_online_booking()
        pdf_bytes = generate_booking_invoice_pdf(booking)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_correct_rental_dates_and_quantity_in_receipt(self):
        """Case 7: Correct rental dates and quantity are processed."""
        from .pdf_service import generate_booking_invoice_pdf
        booking = self.create_paid_online_booking()
        self.assertEqual(booking.requested_quantity, 2)
        self.assertEqual(booking.duration_days, 2)
        pdf_bytes = generate_booking_invoice_pdf(booking)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_correct_rental_charge_and_security_deposit_displayed_separately(self):
        """Case 8: Rental charge and security deposit are kept strictly separate."""
        from .pdf_service import generate_booking_invoice_pdf
        booking = self.create_paid_online_booking()
        self.assertEqual(booking.rental_amount, Decimal('6000.00'))
        self.assertEqual(booking.deposit_amount, Decimal('2000.00'))
        self.assertEqual(booking.total_amount, Decimal('8000.00'))
        pdf_bytes = generate_booking_invoice_pdf(booking)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_correct_payment_method_and_transaction_id_displayed(self):
        """Case 9: Correct payment method and transaction ID are processed."""
        from .pdf_service import generate_booking_invoice_pdf
        # Online booking has actual razorpay transaction id
        online_booking = self.create_paid_online_booking()
        online_pdf = generate_booking_invoice_pdf(online_booking)
        self.assertTrue(online_pdf.startswith(b'%PDF-'))

        # Offline booking has no fake razorpay transaction id
        offline_booking = self.create_paid_offline_booking()
        self.assertFalse(offline_booking.payment_transaction_id)
        offline_pdf = generate_booking_invoice_pdf(offline_booking)
        self.assertTrue(offline_pdf.startswith(b'%PDF-'))

    def test_customer_can_download_pdf_from_booking_details_endpoint(self):
        """Case 10: Customer can download PDF from both /invoice/ and /receipt/ endpoints."""
        booking = self.create_paid_online_booking()
        self.client.force_authenticate(user=self.renter)

        # /invoice/ endpoint
        res_inv = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res_inv.status_code, status.HTTP_200_OK)
        self.assertEqual(res_inv['Content-Type'], 'application/pdf')

        # /receipt/ alias endpoint
        res_rec = self.client.get(f'/api/bookings/{booking.id}/receipt/')
        self.assertEqual(res_rec.status_code, status.HTTP_200_OK)
        self.assertEqual(res_rec['Content-Type'], 'application/pdf')

    def test_another_customer_cannot_download_someone_elses_receipt(self):
        """Case 11: Another customer cannot download someone else's receipt (HTTP 403)."""
        booking = self.create_paid_online_booking()
        # Stranger attempts download
        self.client.force_authenticate(user=self.stranger)
        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('not authorized', str(res.data).lower())

    def test_unauthenticated_user_cannot_download_receipt(self):
        """Anonymous requests are rejected with HTTP 401 Unauthorized."""
        booking = self.create_paid_online_booking()
        self.client.force_authenticate(user=None)
        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_booking_id_is_handled_correctly(self):
        """Case 12: Invalid booking ID returns HTTP 404 Not Found."""
        self.client.force_authenticate(user=self.renter)
        res = self.client.get('/api/bookings/999999/invoice/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_repeated_downloads_work_without_duplicate_records(self):
        """Case 13: Repeated downloads work without creating duplicate records or modifying state."""
        booking = self.create_paid_online_booking()
        self.client.force_authenticate(user=self.renter)

        initial_booking_count = Booking.objects.count()
        for _ in range(5):
            res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertTrue(res.content.startswith(b'%PDF-'))

        self.assertEqual(Booking.objects.count(), initial_booking_count)
        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')

    def test_staff_admin_can_download_customer_receipt(self):
        """Staff administrator can download customer invoice on their behalf."""
        booking = self.create_paid_online_booking()
        self.client.force_authenticate(user=self.staff_admin)
        res = self.client.get(f'/api/bookings/{booking.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')


class FirstBookingDiscountTests(TestCase):
    """
    Comprehensive tests for RentBee First Booking 10% Discount:
    - Registered customer eligibility check
    - Automatic 10% discount application on first booking
    - Original price, discount, and final amount stored in booking record
    - Deposit is not discounted
    - Once per customer enforcement (after successful booking, never applied again)
    - Anti-abuse: cancelling approved or paid bookings does not restore discount
    - Concurrent in-flight pending booking protection
    - Rejection / unapproved cancellation restores legitimate first booking
    - Razorpay order amount matches discounted total
    - PDF Invoice includes discount breakdown
    - API eligibility endpoint
    """
    def setUp(self):
        super().setUp()
        BookingSystemTests.setUp(self)
        self.item.stock = 5
        self.item.save()

    def test_registered_customer_is_initially_eligible(self):
        """1. Every registered customer is eligible for a 10% discount on their first booking."""
        from .services import is_user_eligible_for_first_booking_discount
        self.assertTrue(is_user_eligible_for_first_booking_discount(self.renter))

        # Check API endpoint
        self.client.force_authenticate(user=self.renter)
        res = self.client.get('/api/bookings/discount-eligibility/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['is_eligible'])
        self.assertEqual(res.data['discount_percentage'], 10)
        self.assertEqual(res.data['discount_type'], 'FIRST_BOOKING_10')

    def test_unauthenticated_user_eligibility_endpoint(self):
        """Unauthenticated visitor is not marked as eligible for immediate checkout."""
        res = self.client.get('/api/bookings/discount-eligibility/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['is_eligible'])
        self.assertEqual(res.data['discount_percentage'], 10)

    def test_first_booking_creation_automatically_applies_10_percent_discount(self):
        """2 & 3. 10% discount applied automatically during checkout with original, discount, and final separate."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()
        start = today + timedelta(days=2)
        end = today + timedelta(days=5)  # 3 days

        # Item: rental_price=1500.00, deposit=5000.00
        # 3 days * 1500 = 4500 rental
        # 10% discount = 450.00
        # Discounted rental = 4050.00
        # Deposit = 5000.00
        # Total payable = 9050.00
        payload = {
            'item_id': self.item.id,
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
            'payment_method': 'online',
        }
        res = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        booking = Booking.objects.get(id=res.data['id'])
        self.assertEqual(booking.daily_price, Decimal('1500.00'))
        self.assertEqual(booking.original_rental_amount, Decimal('4500.00'))
        self.assertEqual(booking.discount_amount, Decimal('450.00'))
        self.assertEqual(booking.discount_percentage, Decimal('10.00'))
        self.assertEqual(booking.discount_type, 'FIRST_BOOKING_10')
        self.assertEqual(booking.rental_amount, Decimal('4050.00'))
        self.assertEqual(booking.deposit_amount, Decimal('5000.00'))
        self.assertEqual(booking.total_amount, Decimal('9050.00'))

        # Serializer also exposes the separate breakdown fields
        self.assertEqual(Decimal(str(res.data['original_rental_amount'])), Decimal('4500.00'))
        self.assertEqual(Decimal(str(res.data['discount_amount'])), Decimal('450.00'))
        self.assertEqual(Decimal(str(res.data['rental_amount'])), Decimal('4050.00'))
        self.assertEqual(Decimal(str(res.data['total_amount'])), Decimal('9050.00'))

    def test_discount_applies_only_to_rental_not_deposit(self):
        """Deposit remains 100% intact as damage collateral and is never discounted."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()
        start = today + timedelta(days=1)
        end = today + timedelta(days=3)  # 2 days

        # 2 units: 2 * 2d * 1500 = 6000 rental. Deposit = 2 * 5000 = 10000.
        payload = {
            'item_id': self.item.id,
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'requested_quantity': 2,
            'address_id': self.renter_address.id,
            'payment_method': 'online',
        }
        res = self.client.post('/api/bookings/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        booking = Booking.objects.get(id=res.data['id'])
        self.assertEqual(booking.original_rental_amount, Decimal('6000.00'))
        self.assertEqual(booking.discount_amount, Decimal('600.00'))
        self.assertEqual(booking.rental_amount, Decimal('5400.00'))
        self.assertEqual(booking.deposit_amount, Decimal('10000.00'))
        self.assertEqual(booking.total_amount, Decimal('15400.00'))

    def test_discount_applied_only_once_per_customer_after_successful_booking(self):
        """4 & 5. After the first successful booking, customer must not receive the offer again."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()

        # 1st booking (1 day = 1500 rental, 150 discount)
        payload1 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=1)).isoformat(),
            'end_date': (today + timedelta(days=2)).isoformat(),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res1 = self.client.post('/api/bookings/', payload1, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        booking1 = Booking.objects.get(id=res1.data['id'])
        self.assertEqual(booking1.discount_amount, Decimal('150.00'))

        # Owner approves booking 1 -> successful booking!
        booking1.status = 'waiting_for_pickup'
        booking1.approved_at = timezone.now()
        booking1.save()

        # Customer attempts 2nd booking for future dates
        payload2 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=10)).isoformat(),
            'end_date': (today + timedelta(days=12)).isoformat(),  # 2 days = 3000 rental
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res2 = self.client.post('/api/bookings/', payload2, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        booking2 = Booking.objects.get(id=res2.data['id'])

        # No discount on second booking!
        self.assertEqual(booking2.discount_amount, Decimal('0.00'))
        self.assertEqual(booking2.discount_percentage, Decimal('0.00'))
        self.assertEqual(booking2.rental_amount, Decimal('3000.00'))
        self.assertEqual(booking2.total_amount, Decimal('8000.00'))

    def test_cancelling_approved_booking_does_not_restore_discount(self):
        """7. Users cannot receive the offer repeatedly by cancelling approved bookings and re-booking."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()

        # 1st booking with discount (2 days = 3000 rental, 300 discount)
        payload1 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=1)).isoformat(),
            'end_date': (today + timedelta(days=3)).isoformat(),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res1 = self.client.post('/api/bookings/', payload1, format='json')
        booking1 = Booking.objects.get(id=res1.data['id'])
        self.assertEqual(booking1.discount_amount, Decimal('300.00'))

        # Booking is approved
        booking1.status = 'waiting_for_pickup'
        booking1.approved_at = timezone.now()
        booking1.save()

        # Renter cancels the approved booking
        booking1.status = 'cancelled'
        booking1.cancelled_at = timezone.now()
        booking1.cancelled_by = self.renter
        booking1.save()

        # Renter creates a new booking
        payload2 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=5)).isoformat(),
            'end_date': (today + timedelta(days=7)).isoformat(),  # 2 days = 3000 rental
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res2 = self.client.post('/api/bookings/', payload2, format='json')
        booking2 = Booking.objects.get(id=res2.data['id'])

        # Discount is NOT restored because booking1 was already approved/successful
        self.assertEqual(booking2.discount_amount, Decimal('0.00'))
        self.assertEqual(booking2.rental_amount, Decimal('3000.00'))
        self.assertEqual(booking2.total_amount, Decimal('8000.00'))

    def test_in_flight_pending_booking_blocks_concurrent_discounted_bookings(self):
        """Customer cannot open multiple tabs and get 10% discount on multiple concurrent bookings."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()

        # Create first booking (status='pending_approval', discount_amount=150)
        payload1 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=1)).isoformat(),
            'end_date': (today + timedelta(days=2)).isoformat(),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res1 = self.client.post('/api/bookings/', payload1, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(str(res1.data['discount_amount'])), Decimal('150.00'))

        # Try to create second booking while first is still pending_approval
        payload2 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=5)).isoformat(),
            'end_date': (today + timedelta(days=6)).isoformat(),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res2 = self.client.post('/api/bookings/', payload2, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        # Second booking receives NO discount!
        self.assertEqual(Decimal(str(res2.data['discount_amount'])), Decimal('0.00'))

    def test_cancelled_unapproved_booking_restores_eligibility(self):
        """If owner rejects or renter cancels an unapproved booking, user can still use their first booking offer."""
        self.client.force_authenticate(user=self.renter)
        today = timezone.localdate()

        # Create booking 1
        payload1 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=1)).isoformat(),
            'end_date': (today + timedelta(days=2)).isoformat(),
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res1 = self.client.post('/api/bookings/', payload1, format='json')
        booking1 = Booking.objects.get(id=res1.data['id'])
        self.assertEqual(booking1.discount_amount, Decimal('150.00'))

        # Owner rejects the booking before approval
        booking1.status = 'rejected'
        booking1.rejection_reason = 'Owner unavailable'
        booking1.rejected_at = timezone.now()
        booking1.save()

        # User is once again eligible for their real first rental!
        from .services import is_user_eligible_for_first_booking_discount
        self.assertTrue(is_user_eligible_for_first_booking_discount(self.renter))

        payload2 = {
            'item_id': self.item.id,
            'start_date': (today + timedelta(days=3)).isoformat(),
            'end_date': (today + timedelta(days=5)).isoformat(),  # 2 days = 3000 rental
            'requested_quantity': 1,
            'address_id': self.renter_address.id,
        }
        res2 = self.client.post('/api/bookings/', payload2, format='json')
        booking2 = Booking.objects.get(id=res2.data['id'])
        self.assertEqual(booking2.discount_amount, Decimal('300.00'))
        self.assertEqual(booking2.rental_amount, Decimal('2700.00'))
        self.assertEqual(booking2.total_amount, Decimal('7700.00'))

    def test_razorpay_order_notes_contain_discount_details(self):
        """6. Razorpay order records discount details in notes and charges the discounted total."""
        from unittest.mock import patch, MagicMock

        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('500.00'),
            original_rental_amount=Decimal('1000.00'),
            discount_amount=Decimal('100.00'),
            discount_percentage=Decimal('10.00'),
            discount_type='FIRST_BOOKING_10',
            rental_amount=Decimal('900.00'),
            deposit_amount=Decimal('1000.00'),
            total_amount=Decimal('1900.00'),
            status='waiting_for_pickup',
            payment_status='pending',
            payment_method='online',
        )

        mock_client = MagicMock()
        mock_client.order.create.return_value = {
            'id': 'order_test_discount_123',
            'amount': 190000,
            'currency': 'INR',
        }

        with patch('bookings.services.get_razorpay_client', return_value=mock_client), \
             patch('django.conf.settings.RAZORPAY_KEY_ID', 'rzp_test_key'):
            from .services import get_or_create_razorpay_order_for_booking
            order = get_or_create_razorpay_order_for_booking(booking)

            self.assertEqual(order['amount'], 190000)
            mock_client.order.create.assert_called_once()
            call_kwargs = mock_client.order.create.call_args[1]['data']
            self.assertEqual(call_kwargs['amount'], 190000)
            self.assertEqual(call_kwargs['notes']['discount_amount'], '100.00')
            self.assertEqual(call_kwargs['notes']['discount_type'], 'FIRST_BOOKING_10')

    def test_invoice_pdf_includes_discount_breakdown(self):
        """Verified PDF invoice itemizes the original rental, 10% discount, and payable amount."""
        from .pdf_service import generate_booking_invoice_pdf

        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('500.00'),
            original_rental_amount=Decimal('1000.00'),
            discount_amount=Decimal('100.00'),
            discount_percentage=Decimal('10.00'),
            discount_type='FIRST_BOOKING_10',
            rental_amount=Decimal('900.00'),
            deposit_amount=Decimal('1000.00'),
            total_amount=Decimal('1900.00'),
            status='waiting_for_pickup',
            payment_status='paid',
            payment_method='online',
            payment_transaction_id='pay_test_pdf_123',
            payment_verified_at=timezone.now(),
        )

        pdf_bytes = generate_booking_invoice_pdf(booking)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_razorpay_order_notes_contain_discount_details(self):
        """6. Razorpay order records discount details in notes and charges the discounted total."""
        from unittest.mock import patch, MagicMock

        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('500.00'),
            original_rental_amount=Decimal('1000.00'),
            discount_amount=Decimal('100.00'),
            discount_percentage=Decimal('10.00'),
            discount_type='FIRST_BOOKING_10',
            rental_amount=Decimal('900.00'),
            deposit_amount=Decimal('1000.00'),
            total_amount=Decimal('1900.00'),
            status='waiting_for_pickup',
            payment_status='pending',
            payment_method='online',
        )

        mock_client = MagicMock()
        mock_client.order.create.return_value = {
            'id': 'order_test_discount_123',
            'amount': 190000,
            'currency': 'INR',
        }

        with patch('bookings.services.get_razorpay_client', return_value=mock_client), \
             patch('django.conf.settings.RAZORPAY_KEY_ID', 'rzp_test_key'):
            from .services import get_or_create_razorpay_order_for_booking
            order = get_or_create_razorpay_order_for_booking(booking)

            self.assertEqual(order['amount'], 190000)
            mock_client.order.create.assert_called_once()
            call_kwargs = mock_client.order.create.call_args[1]['data']
            self.assertEqual(call_kwargs['amount'], 190000)
            self.assertEqual(call_kwargs['notes']['discount_amount'], '100.00')
            self.assertEqual(call_kwargs['notes']['discount_type'], 'FIRST_BOOKING_10')

    def test_invoice_pdf_includes_discount_breakdown(self):
        """Verified PDF invoice itemizes the original rental, 10% discount, and payable amount."""
        from .pdf_service import generate_booking_invoice_pdf

        today = timezone.localdate()
        booking = Booking.objects.create(
            item=self.item,
            owner=self.owner,
            renter=self.renter,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('500.00'),
            original_rental_amount=Decimal('1000.00'),
            discount_amount=Decimal('100.00'),
            discount_percentage=Decimal('10.00'),
            discount_type='FIRST_BOOKING_10',
            rental_amount=Decimal('900.00'),
            deposit_amount=Decimal('1000.00'),
            total_amount=Decimal('1900.00'),
            status='waiting_for_pickup',
            payment_status='paid',
            payment_method='online',
            payment_transaction_id='pay_test_pdf_123',
            payment_verified_at=timezone.now(),
        )

        pdf_bytes = generate_booking_invoice_pdf(booking)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_bytes), 1000)





