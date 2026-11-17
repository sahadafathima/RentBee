import hashlib
import hmac
import json
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
from bookings.models import Booking, ProcessedWebhookEvent
from bookings.services import initiate_booking_refund, confirm_offline_refund

User = get_user_model()


@override_settings(
    RAZORPAY_KEY_ID='rzp_test_key123',
    RAZORPAY_KEY_SECRET='rzp_test_secret123',
    RAZORPAY_WEBHOOK_SECRET='rzp_wh_secret123'
)
class BookingCancellationAndRefundTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.owner = User.objects.create_user(
            email='alice.owner@test.com',
            password='Password123!',
            full_name='Alice Host',
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
            full_name='Alice Host',
            house_number='House 10',
            address='Indiranagar 100ft Rd',
            area='Indiranagar',
            landmark='Opp Metro',
            city='Bangalore',
            state='Karnataka',
            pincode='560038',
            country='India',
            address_type='Home'
        )
        self.renter_address = Address.objects.create(
            user=self.renter,
            full_name='Bob Renter',
            house_number='Apt 202',
            address='Koramangala 4th Block',
            area='Koramangala',
            landmark='Near Sony World',
            city='Bangalore',
            state='Karnataka',
            pincode='560034',
            country='India',
            address_type='Home'
        )

        # Category & Item
        self.category = Category.objects.create(name='Cameras', icon='📷', is_active=True)
        self.item = Item.objects.create(
            name='Sony A7 IV Camera Kit',
            category=self.category,
            owner=self.owner,
            rental_price=Decimal('2000.00'),
            deposit=Decimal('1000.00'),
            stock=3,
            is_published=True
        )

    def _create_booking(self, status='pending_approval', payment_method='online', payment_status='pending',
                        rental_amount=Decimal('4000.00'), deposit_amount=Decimal('1000.00'),
                        total_amount=Decimal('5000.00'), payment_transaction_id=''):
        start_date = timezone.localdate() + timedelta(days=2)
        end_date = start_date + timedelta(days=2)
        return Booking.objects.create(
            renter=self.renter,
            item=self.item,
            owner=self.owner,
            start_date=start_date,
            end_date=end_date,
            duration_days=2,
            requested_quantity=1,
            daily_price=Decimal('2000.00'),
            rental_amount=rental_amount,
            deposit_amount=deposit_amount,
            total_amount=total_amount,
            status=status,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_transaction_id=payment_transaction_id,
            renter_address=self.renter_address,
        )

    # =========================================================================
    # 1. CANCELLATION SCENARIOS
    # =========================================================================

    def test_scenario_a_unpaid_booking_cancelled_before_approval(self):
        """Scenario A: Booking cancelled before owner approval (pending_approval, unpaid)."""
        booking = self._create_booking(status='pending_approval', payment_status='pending')
        self.client.force_authenticate(user=self.renter)

        with patch('bookings.services.get_razorpay_client') as mock_client:
            res = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'Change of plans'})
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            # Razorpay must NOT be called
            mock_client.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.cancellation_reason, 'Change of plans')
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual(booking.cancelled_by, self.renter)
        self.assertEqual(booking.payment_status, 'pending')
        self.assertEqual(booking.refund_status, '')

    def test_scenario_b_approved_unpaid_booking_cancelled(self):
        """Scenario B: Booking approved but payment not completed (waiting_for_pickup, unpaid)."""
        booking = self._create_booking(status='waiting_for_pickup', payment_status='pending')
        self.client.force_authenticate(user=self.renter)

        with patch('bookings.services.get_razorpay_client') as mock_client:
            res = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'Found another camera'})
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_client.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.payment_status, 'pending')
        self.assertEqual(booking.refund_status, '')

    @patch('bookings.services.get_razorpay_client')
    def test_scenario_c_paid_online_booking_cancelled_initiates_100_percent_refund(self, mock_get_client):
        """Scenario C: Booking approved, online payment completed (₹5,000 paid) -> 100% refund."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch_multiple_refund.return_value = {'count': 0, 'items': []}
        mock_rzp.payment.refund.return_value = {
            'id': 'rfnd_test_abc123',
            'entity': 'refund',
            'amount': 500000,
            'currency': 'INR',
            'status': 'pending',
            'payment_id': 'pay_test_online123'
        }

        booking = self._create_booking(
            status='waiting_for_pickup',
            payment_method='online',
            payment_status='paid',
            rental_amount=Decimal('4000.00'),
            deposit_amount=Decimal('1000.00'),
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_test_online123'
        )
        self.client.force_authenticate(user=self.renter)

        res = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'Trip postponed'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verify Razorpay refund API was called with exact payment ID and full amount in paise
        mock_rzp.payment.refund.assert_called_once()
        call_args = mock_rzp.payment.refund.call_args
        self.assertEqual(call_args[0][0], 'pay_test_online123')
        self.assertEqual(call_args[0][1]['amount'], 500000)  # ₹5,000 in paise
        self.assertEqual(call_args[0][1]['notes']['cancellation_fee'], '0.00')

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        # Payment status must remain 'paid' while refund is pending
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.refund_status, 'pending')
        self.assertEqual(booking.refund_transaction_id, 'rfnd_test_abc123')
        self.assertEqual(booking.refund_amount, Decimal('5000.00'))
        self.assertEqual(booking.payment_transaction_id, 'pay_test_online123')  # Preserved!

    def test_scenario_d_cancellation_blocked_after_pickup(self):
        """Scenario D: Once pickup is confirmed (rental_in_progress), cancellation must be rejected."""
        booking = self._create_booking(
            status='rental_in_progress',
            payment_method='online',
            payment_status='paid',
            payment_transaction_id='pay_active_rental'
        )
        self.client.force_authenticate(user=self.renter)

        with patch('bookings.services.get_razorpay_client') as mock_client:
            res = self.client.post(f'/api/bookings/{booking.id}/cancel/')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Cannot cancel a rental that is already in progress or completed', res.data.get('error', ''))
            mock_client.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'rental_in_progress')

    def test_scenario_e_cancellation_blocked_after_completion(self):
        """Scenario E: Once completed, normal cancellation must not be allowed."""
        booking = self._create_booking(
            status='completed',
            payment_method='online',
            payment_status='paid',
            payment_transaction_id='pay_completed_rental'
        )
        self.client.force_authenticate(user=self.renter)

        with patch('bookings.services.get_razorpay_client') as mock_client:
            res = self.client.post(f'/api/bookings/{booking.id}/cancel/')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            mock_client.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')

    def test_stranger_cannot_cancel_booking(self):
        """Another renter cannot cancel the booking (HTTP 403)."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.stranger)

        res = self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending_approval')

    def test_staff_admin_can_cancel_booking(self):
        """Staff administrator can cancel a booking on behalf of renter."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.staff_admin)

        res = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'Admin action'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.cancelled_by, self.staff_admin)

    def test_duplicate_cancellation_requests_handled_safely(self):
        """Second cancellation request returns HTTP 400 and does not duplicate actions."""
        booking = self._create_booking(status='pending_approval')
        self.client.force_authenticate(user=self.renter)

        res1 = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'First cancel'})
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        res2 = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'reason': 'Second cancel'})
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # 2. REFUND TESTS
    # =========================================================================

    @patch('bookings.services.get_razorpay_client')
    def test_refund_includes_both_rental_and_security_deposit(self, mock_get_client):
        """Full captured amount includes rental amount and security deposit."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch_multiple_refund.return_value = {'count': 0, 'items': []}
        mock_rzp.payment.refund.return_value = {
            'id': 'rfnd_split_check',
            'amount': 500000,
            'status': 'pending',
            'currency': 'INR'
        }

        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            rental_amount=Decimal('4000.00'),
            deposit_amount=Decimal('1000.00'),
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_split_123'
        )

        result = initiate_booking_refund(booking)
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['refund_id'], 'rfnd_split_check')

        call_data = mock_rzp.payment.refund.call_args[0][1]
        self.assertEqual(call_data['amount'], 500000)

    @patch('bookings.services.get_razorpay_client')
    def test_refund_request_stored_as_pending_until_confirmation(self, mock_get_client):
        """Payment status remains 'paid' and refund_status becomes 'pending' when accepted."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch_multiple_refund.return_value = {'count': 0, 'items': []}
        mock_rzp.payment.refund.return_value = {
            'id': 'rfnd_pending_status',
            'amount': 300000,
            'status': 'pending',
            'currency': 'INR'
        }

        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('3000.00'),
            payment_transaction_id='pay_pending_test'
        )

        initiate_booking_refund(booking)
        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'pending')
        self.assertEqual(booking.payment_status, 'paid')  # Must NOT be marked refunded yet!
        self.assertIsNone(booking.refunded_at)

    @patch('bookings.services.get_razorpay_client')
    def test_immediate_processed_refund_marks_payment_as_refunded(self, mock_get_client):
        """If Razorpay synchronously returns 'processed', payment_status becomes 'refunded'."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch_multiple_refund.return_value = {'count': 0, 'items': []}
        mock_rzp.payment.refund.return_value = {
            'id': 'rfnd_processed_instant',
            'amount': 300000,
            'status': 'processed',
            'currency': 'INR'
        }

        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('3000.00'),
            payment_transaction_id='pay_instant_proc'
        )

        initiate_booking_refund(booking)
        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'processed')
        self.assertEqual(booking.payment_status, 'refunded')
        self.assertIsNotNone(booking.refunded_at)

    @patch('bookings.services.get_razorpay_client')
    def test_failed_refund_does_not_mark_payment_as_refunded(self, mock_get_client):
        """Failed refund sets refund_status='failed' and keeps payment_status='paid'."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch_multiple_refund.return_value = {'count': 0, 'items': []}
        mock_rzp.payment.refund.side_effect = Exception("Razorpay internal server error")

        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('3000.00'),
            payment_transaction_id='pay_failed_refund'
        )

        result = initiate_booking_refund(booking)
        self.assertEqual(result['status'], 'failed')

        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'failed')
        self.assertEqual(booking.payment_status, 'paid')
        self.assertIn("Razorpay internal server error", booking.refund_error)

    @patch('bookings.services.get_razorpay_client')
    def test_duplicate_refund_requests_do_not_create_duplicate_refunds(self, mock_get_client):
        """Duplicate refund requests reuse the existing refund ID rather than calling refund API again."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.refund.fetch.return_value = {
            'id': 'rfnd_already_exists',
            'amount': 500000,
            'status': 'processed'
        }

        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_idem_check'
        )
        booking.refund_transaction_id = 'rfnd_already_exists'
        booking.refund_status = 'pending'
        booking.save()

        initiate_booking_refund(booking)
        # client.payment.refund must NOT be called again
        mock_rzp.payment.refund.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'processed')
        self.assertEqual(booking.payment_status, 'refunded')

    @patch('bookings.services.get_razorpay_client')
    def test_network_timeout_reconciles_existing_refund(self, mock_get_client):
        """If timeout occurs, service checks fetch_multiple_refund and reconciles instead of duplicate."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        # When creating refund, raises timeout
        mock_rzp.payment.refund.side_effect = Exception("Connection timed out after 30s")
        # But reconciliation reveals the refund actually was created on Razorpay!
        mock_rzp.payment.fetch_multiple_refund.return_value = {
            'count': 1,
            'items': [{
                'id': 'rfnd_reconciled_after_timeout',
                'amount': 500000,
                'status': 'processed',
                'currency': 'INR'
            }]
        }

        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_timeout_test'
        )

        result = initiate_booking_refund(booking)
        self.assertTrue(result.get('reconciled'))
        self.assertEqual(result.get('refund_id'), 'rfnd_reconciled_after_timeout')

        booking.refresh_from_db()
        self.assertEqual(booking.refund_transaction_id, 'rfnd_reconciled_after_timeout')
        self.assertEqual(booking.refund_status, 'processed')
        self.assertEqual(booking.payment_status, 'refunded')

    # =========================================================================
    # 3. WEBHOOK REFUND TESTS
    # =========================================================================

    def _generate_webhook_signature(self, body_str):
        secret = 'rzp_wh_secret123'
        return hmac.new(secret.encode('utf-8'), body_str.encode('utf-8'), hashlib.sha256).hexdigest()

    def test_webhook_refund_created_event(self):
        """refund.created webhook sets refund_status='pending' and keeps payment_status='paid'."""
        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_wh_rf_created'
        )

        payload = {
            'id': 'evt_rf_created_1',
            'event': 'refund.created',
            'payload': {
                'refund': {
                    'entity': {
                        'id': 'rfnd_wh_001',
                        'payment_id': 'pay_wh_rf_created',
                        'amount': 500000,
                        'status': 'created',
                    }
                }
            }
        }
        raw_body = json.dumps(payload)
        sig = self._generate_webhook_signature(raw_body)

        res = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'pending')
        self.assertEqual(booking.payment_status, 'paid')  # Remains paid
        self.assertEqual(booking.refund_transaction_id, 'rfnd_wh_001')

    def test_webhook_refund_processed_event(self):
        """refund.processed webhook updates payment_status='refunded' and sets refunded_at."""
        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_wh_rf_proc'
        )
        booking.refund_transaction_id = 'rfnd_wh_002'
        booking.refund_status = 'pending'
        booking.save()

        payload = {
            'id': 'evt_rf_processed_1',
            'event': 'refund.processed',
            'payload': {
                'refund': {
                    'entity': {
                        'id': 'rfnd_wh_002',
                        'payment_id': 'pay_wh_rf_proc',
                        'amount': 500000,
                        'status': 'processed',
                    }
                }
            }
        }
        raw_body = json.dumps(payload)
        sig = self._generate_webhook_signature(raw_body)

        res = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'processed')
        self.assertEqual(booking.payment_status, 'refunded')
        self.assertIsNotNone(booking.refunded_at)

    def test_webhook_refund_failed_event(self):
        """refund.failed webhook sets refund_status='failed' and keeps payment_status='paid'."""
        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_wh_rf_fail'
        )
        booking.refund_transaction_id = 'rfnd_wh_003'
        booking.refund_status = 'pending'
        booking.save()

        payload = {
            'id': 'evt_rf_failed_1',
            'event': 'refund.failed',
            'payload': {
                'refund': {
                    'entity': {
                        'id': 'rfnd_wh_003',
                        'payment_id': 'pay_wh_rf_fail',
                        'amount': 500000,
                        'status': 'failed',
                    }
                }
            }
        }
        raw_body = json.dumps(payload)
        sig = self._generate_webhook_signature(raw_body)

        res = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'failed')
        self.assertEqual(booking.payment_status, 'paid')  # Remains paid!

    def test_webhook_idempotency_duplicate_events(self):
        """Duplicate webhook event delivery is idempotent via ProcessedWebhookEvent."""
        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_wh_rf_idem'
        )

        payload = {
            'id': 'evt_rf_idem_999',
            'event': 'refund.processed',
            'payload': {
                'refund': {
                    'entity': {
                        'id': 'rfnd_wh_idem',
                        'payment_id': 'pay_wh_rf_idem',
                        'amount': 500000,
                        'status': 'processed',
                    }
                }
            }
        }
        raw_body = json.dumps(payload)
        sig = self._generate_webhook_signature(raw_body)

        # First delivery
        res1 = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data.get('status'), 'success')

        # Second delivery of same event
        res2 = self.client.post(
            '/api/bookings/payment-webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data.get('status'), 'already_processed')

    # =========================================================================
    # 4. OFFLINE PAYMENT CANCELLATION TESTS
    # =========================================================================

    def test_offline_unpaid_cancellation_no_refund(self):
        """Offline unpaid booking cancellation does not initiate refund."""
        booking = self._create_booking(
            status='waiting_for_pickup',
            payment_method='offline',
            payment_status='pending'
        )
        self.client.force_authenticate(user=self.renter)

        with patch('bookings.services.get_razorpay_client') as mock_client:
            res = self.client.post(f'/api/bookings/{booking.id}/cancel/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_client.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.payment_status, 'pending')
        self.assertEqual(booking.refund_status, '')

    def test_offline_paid_cancellation_does_not_call_razorpay(self):
        """Offline paid booking cancellation does not call Razorpay; marks cash return as pending."""
        booking = self._create_booking(
            status='waiting_for_pickup',
            payment_method='offline',
            payment_status='paid',
            total_amount=Decimal('5000.00')
        )
        self.client.force_authenticate(user=self.renter)

        with patch('bookings.services.get_razorpay_client') as mock_client:
            res = self.client.post(f'/api/bookings/{booking.id}/cancel/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_client.assert_not_called()

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        # Payment status remains 'paid' until cash return is confirmed
        self.assertEqual(booking.payment_status, 'paid')
        self.assertEqual(booking.refund_status, 'pending')
        self.assertIsNone(booking.cash_returned_at)

    def test_owner_can_confirm_offline_cash_refund(self):
        """Owner confirms manual cash refund to renter -> payment_status='refunded'."""
        booking = self._create_booking(
            status='cancelled',
            payment_method='offline',
            payment_status='paid',
            total_amount=Decimal('5000.00')
        )
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-refund/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'refunded')
        self.assertEqual(booking.refund_status, 'processed')
        self.assertIsNotNone(booking.cash_returned_at)
        self.assertEqual(booking.cash_returned_by, self.owner)

    def test_renter_forbidden_from_confirming_own_offline_cash_refund(self):
        """Renter attempting to confirm their own cash return gets HTTP 403."""
        booking = self._create_booking(
            status='cancelled',
            payment_method='offline',
            payment_status='paid',
            total_amount=Decimal('5000.00')
        )
        self.client.force_authenticate(user=self.renter)

        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-refund/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'paid')
        self.assertIsNone(booking.cash_returned_at)

    def test_stranger_forbidden_from_confirming_offline_cash_refund(self):
        """Unrelated stranger cannot confirm offline cash refund (HTTP 403)."""
        booking = self._create_booking(
            status='cancelled',
            payment_method='offline',
            payment_status='paid',
            total_amount=Decimal('5000.00')
        )
        self.client.force_authenticate(user=self.stranger)

        res = self.client.post(f'/api/bookings/{booking.id}/confirm-offline-refund/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # 5. RETRY REFUND ENDPOINT TEST
    # =========================================================================

    @patch('bookings.services.get_razorpay_client')
    def test_renter_can_retry_failed_refund(self, mock_get_client):
        """Renter can retry a failed online refund via retry-refund endpoint."""
        mock_rzp = MagicMock()
        mock_get_client.return_value = mock_rzp
        mock_rzp.payment.fetch_multiple_refund.return_value = {'count': 0, 'items': []}
        mock_rzp.payment.refund.return_value = {
            'id': 'rfnd_retry_success',
            'amount': 500000,
            'status': 'processed',
            'currency': 'INR'
        }

        booking = self._create_booking(
            status='cancelled',
            payment_method='online',
            payment_status='paid',
            total_amount=Decimal('5000.00'),
            payment_transaction_id='pay_retry_test'
        )
        booking.refund_status = 'failed'
        booking.refund_error = 'Gateway timeout'
        booking.save()

        self.client.force_authenticate(user=self.renter)
        res = self.client.post(f'/api/bookings/{booking.id}/retry-refund/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        self.assertEqual(booking.refund_status, 'processed')
        self.assertEqual(booking.payment_status, 'refunded')
        self.assertEqual(booking.refund_transaction_id, 'rfnd_retry_success')
