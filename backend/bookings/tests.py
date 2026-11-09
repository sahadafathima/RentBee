from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from addresses.models import Address
from catalog.models import Category, Item
from .models import Booking, IssueReport, AvailabilityNotificationRequest, InAppNotification
from .admin import verify_payment_action
from .services import mark_booking_payment_verified, expire_stale_pending_bookings

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
        self.assertEqual(Decimal(str(data['rental_amount'])), Decimal('4500.00'))
        self.assertEqual(Decimal(str(data['deposit_amount'])), Decimal('5000.00'))
        self.assertEqual(Decimal(str(data['total_amount'])), Decimal('9500.00'))
        self.assertEqual(data['status'], 'pending_approval')
        self.assertEqual(data['payment_status'], 'pending')

        # Verify snapshot isolation: mutating item rental price later does not affect booking
        self.item.rental_price = Decimal('9999.00')
        self.item.save()

        booking = Booking.objects.get(id=data['id'])
        self.assertEqual(booking.daily_price, Decimal('1500.00'))
        self.assertEqual(booking.total_amount, Decimal('9500.00'))

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
        self.assertEqual(Decimal(str(res_1day.data['rental_amount'])), Decimal('1500.00'))

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
        self.assertEqual(Decimal(str(res_2day.data['rental_amount'])), Decimal('3000.00'))

        Booking.objects.filter(id=res_2day.data['id']).update(status='cancelled')

        # 3-day rental: 9th to 12th = 3 days
        res_3day = self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(today + timedelta(days=1)),
            'end_date': str(today + timedelta(days=4)),
        }, format='json')
        self.assertEqual(res_3day.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_3day.data['duration_days'], 3)
        self.assertEqual(Decimal(str(res_3day.data['rental_amount'])), Decimal('4500.00'))

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
        """Conflicting bookings for the same item are blocked."""
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
        self.assertIn('already booked or reserved', str(res2.data))

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
        res_fail = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/')
        self.assertEqual(res_fail.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('payment is verified', str(res_fail.data))

        # Authorized backend payment verification (e.g. staff admin)
        mark_booking_payment_verified(booking, verified_by=self.staff_admin, transaction_id='TXN-TEST-123')
        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.payment_verified_by, self.staff_admin)
        self.assertIsNotNone(booking.payment_verified_at)

        # Pickup confirmation now succeeds
        res_success = self.client.post(f'/api/bookings/{booking.id}/confirm-pickup/')
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

    def test_cancellation_pre_pickup_restriction(self):
        """Cancellation allowed only in pending_approval & waiting_for_pickup; blocked in rental_in_progress."""
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

        # Renter cancels before pickup -> succeeds
        self.client.force_authenticate(user=self.renter)
        res_cancel = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'Change of plans'})
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.cancellation_reason, 'Change of plans')

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

        # Create booking for these dates
        self.client.force_authenticate(user=self.renter)
        self.client.post('/api/bookings/', {
            'item_id': self.item.id,
            'start_date': str(start),
            'end_date': str(end),
        }, format='json')

        # After booking: Booked
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


