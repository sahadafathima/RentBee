from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from addresses.models import Address
from catalog.models import Category, Item
from .models import Booking, IssueReport, AvailabilityNotificationRequest, InAppNotification, PushSubscription
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
        self.assertEqual(Decimal(str(response.data['rental_amount'])), Decimal('9000.00'))
        self.assertEqual(Decimal(str(response.data['deposit_amount'])), Decimal('15000.00'))
        self.assertEqual(Decimal(str(response.data['total_amount'])), Decimal('24000.00'))
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
        self.assertEqual(self.client.post(f'/api/bookings/{active}/confirm-pickup/').status_code, status.HTTP_200_OK)
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
            status=initial, payment_status='paid')
        barrier = Barrier(2)
        def submit(action):
            close_old_connections()
            try:
                endpoint, user_id = action
                client = APIClient()
                client.force_authenticate(User.objects.get(pk=user_id))
                barrier.wait(timeout=10)
                return client.post(f'/api/bookings/{booking.pk}/{endpoint}/').status_code
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
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/reject/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/bookings/{pk}/reject/').status_code, 400)
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
            self.assertIn('declined', sent_data['body'].lower())
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

