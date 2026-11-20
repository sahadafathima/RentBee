import json
import logging
import secrets
from datetime import timedelta
from django.contrib.auth.hashers import make_password, check_password
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .sms_service import send_pickup_otp_sms, mask_phone, SMSConfigurationError, SMSSendError

logger = logging.getLogger(__name__)

from catalog.models import Item
from .models import Booking, IssueReport, AvailabilityNotificationRequest, InAppNotification, PushSubscription
from .push_service import get_vapid_public_key, send_web_push
from .serializers import (
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingListSerializer,
    IssueReportSerializer,
    InAppNotificationSerializer,
    PaymentVerifySerializer,
)
from .services import (
    expire_stale_pending_bookings,
    get_item_availability,
    locked_booking_transition,
    notify_booking_event,
    process_availability_notifications_for_item,
    get_or_create_razorpay_order_for_booking,
    verify_razorpay_payment,
    verify_webhook_signature,
    process_razorpay_webhook_event,
    confirm_offline_booking_payment,
    confirm_offline_refund,
    initiate_booking_refund,
    is_user_eligible_for_first_booking_discount,
)


class MyBookingsListView(APIView):
   
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Opportunistic just-in-time expiry
        expire_stale_pending_bookings()

        user = request.user
        base_qs = Booking.objects.filter(renter=user).select_related(
            'item', 'item__category', 'owner', 'owner__profile'
        ).prefetch_related('item__images')

        # Dynamic counts across all user bookings
        counts = {
            'all': base_qs.count(),
            'incoming': base_qs.filter(status='pending_approval').count(),
            'accepted': base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress']).count(),
            'active': base_qs.filter(status__in=['pending_approval', 'waiting_for_pickup', 'rental_in_progress']).count(),
            'rejected': base_qs.filter(status='rejected').count(),
            'completed': base_qs.filter(status='completed').count(),
            'cancelled': base_qs.filter(status__in=['cancelled', 'rejected', 'expired']).count(),
        }

        tab = request.query_params.get('tab', 'all').lower()
        if tab in ['incoming', 'pending']:
            qs = base_qs.filter(status='pending_approval')
        elif tab == 'accepted':
            qs = base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress'])
        elif tab == 'active':
            qs = base_qs.filter(status__in=['pending_approval', 'waiting_for_pickup', 'rental_in_progress'])
        elif tab == 'rejected':
            qs = base_qs.filter(status='rejected')
        elif tab == 'completed':
            qs = base_qs.filter(status='completed')
        elif tab == 'cancelled':
            qs = base_qs.filter(status__in=['cancelled', 'rejected', 'expired'])
        else:
            qs = base_qs

        # Backend search by item name or owner name
        if search := request.query_params.get('search'):   # := used to check and store simultaneously#
            search = search.strip()
            if search:
                qs = qs.filter(
                    Q(item__name__icontains=search) |
                    Q(owner__full_name__icontains=search) |
                    Q(owner__email__icontains=search) |
                    Q(booking_reference__icontains=search)
                )

        try:
            page_num = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page_num = 1

        try:
            page_size = max(1, min(100, int(request.query_params.get('page_size', 6))))
        except (ValueError, TypeError):
            page_size = 6

        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page_num)

        serializer = BookingListSerializer(page_obj.object_list, many=True, context={'request': request})

        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'counts': counts,
            'results': serializer.data,
        })


class BookingCreateView(APIView):
    """
    Renter creates a new booking request.
    Calculates prices on backend, checks availability & row-locking, snapshots owner and prices.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        expire_stale_pending_bookings()
        serializer = BookingCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        detail_serializer = BookingDetailSerializer(booking, context={'request': request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class BookingDetailView(APIView):
    """
    Complete booking details endpoint.
    Strict privacy: only authorized participants (renter, owner, staff) can access.
    Owner pickup address is redacted during pending_approval.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        expire_stale_pending_bookings()

        booking = get_object_or_404(
            Booking.objects.select_related(
                'item', 'item__category', 'owner', 'owner__profile', 'renter'
            ).prefetch_related('item__images', 'owner__addresses', 'issue_reports'),
            pk=pk
        )

        # Participant Authorization Check
        is_participant = (
            booking.renter_id == request.user.id or
            booking.owner_id == request.user.id or
            request.user.is_staff
        )
        if not is_participant:
            return Response(
                {'error': 'You do not have permission to view this booking.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = BookingDetailSerializer(booking, context={'request': request})
        return Response(serializer.data)


class CancelBookingView(APIView):
    """
    Renter cancellation endpoint.
    Allowed strictly before pickup (during pending_approval or waiting_for_pickup).
    Strictly forbidden during rental_in_progress or completed.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def _execute_cancellation_transition(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.renter_id != request.user.id and not request.user.is_staff:
            return None, False, Response(
                {'error': 'Only the booking renter can cancel this booking.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status in ['rental_in_progress', 'completed']:
            return None, False, Response(
                {'error': 'Cannot cancel a rental that is already in progress or completed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if booking.status in ['cancelled', 'rejected', 'expired']:
            return None, False, Response(
                {'error': f'Booking is already {booking.get_status_display().lower()}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not booking.can_renter_cancel():
            return None, False, Response(
                {'error': f'Cannot cancel booking with current status: {booking.get_status_display()}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '').strip()
        booking.status = 'cancelled'
        booking.cancelled_at = timezone.now()
        booking.cancelled_by = request.user
        booking.cancellation_reason = reason

        is_online_paid = (
            getattr(booking, 'payment_method', 'online') == 'online'
            and booking.payment_status == 'paid'
        )
        is_offline_paid = (
            getattr(booking, 'payment_method', 'online') == 'offline'
            and booking.payment_status == 'paid'
        )

        update_fields = ['status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at']

        if is_online_paid:
            booking.refund_amount = booking.total_amount
            booking.refund_status = 'pending'
            booking.refund_initiated_at = timezone.now()
            update_fields.extend(['refund_amount', 'refund_status', 'refund_initiated_at'])
        elif is_offline_paid:
            booking.refund_amount = booking.total_amount
            booking.refund_status = 'pending'
            update_fields.extend(['refund_amount', 'refund_status'])

        booking.save(update_fields=update_fields)

        # Notify users who requested availability notifications for this item
        transaction.on_commit(
            lambda item_id=booking.item_id: process_availability_notifications_for_item(item_id)
        )

        return booking, is_online_paid, None

    def post(self, request, pk):
        booking, is_online_paid, err_response = self._execute_cancellation_transition(request, pk)
        if err_response:
            return err_response

        # Outside the locked database transaction, call Razorpay refund API
        if is_online_paid:
            try:
                initiate_booking_refund(booking.id)
                booking.refresh_from_db()
            except Exception as e:
                logger.error(
                    f"Failed to initiate refund during cancellation for booking {booking.id} "
                    f"({booking.booking_reference}): {e}",
                    exc_info=True
                )
                booking.refresh_from_db()
                if booking.refund_status != 'failed':
                    booking.refund_status = 'failed'
                    booking.refund_error = str(e)
                    booking.save(update_fields=['refund_status', 'refund_error', 'updated_at'])

        return Response({
            'message': 'Booking cancelled successfully.',
            'booking_id': booking.id,
            'status': booking.status,
            'payment_status': booking.payment_status,
            'refund_status': booking.refund_status or None,
            'refund_amount': str(booking.refund_amount) if booking.refund_amount is not None else None,
            'refund_transaction_id': booking.refund_transaction_id or None,
            'refund_error': booking.refund_error or None,
            'booking': BookingDetailSerializer(booking, context={'request': request}).data
        })


class RetryBookingRefundView(APIView):
    """
    Renter or staff admin retries/reconciles a pending or failed refund for a cancelled booking.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        if booking.renter_id != request.user.id and not request.user.is_staff:
            return Response({'error': 'Only the renter can retry refund.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.status != 'cancelled':
            return Response({'error': 'Refund can only be retried for cancelled bookings.'}, status=status.HTTP_400_BAD_REQUEST)

        if getattr(booking, 'payment_method', 'online') == 'offline':
            return Response({'error': 'Offline bookings cannot use Razorpay refund retry.'}, status=status.HTTP_400_BAD_REQUEST)

        if booking.refund_status == 'processed':
            return Response({
                'message': 'Refund is already completed.',
                'refund_status': 'processed',
                'refund_transaction_id': booking.refund_transaction_id,
                'refund_amount': str(booking.refund_amount or booking.total_amount),
            })

        initiate_booking_refund(booking.id)
        booking.refresh_from_db()
        return Response({
            'message': 'Refund processing initiated.',
            'booking_id': booking.id,
            'refund_status': booking.refund_status,
            'refund_amount': str(booking.refund_amount) if booking.refund_amount is not None else None,
            'refund_transaction_id': booking.refund_transaction_id or None,
            'refund_error': booking.refund_error or None,
            'payment_status': booking.payment_status,
            'booking': BookingDetailSerializer(booking, context={'request': request}).data
        })


class ConfirmOfflineRefundView(APIView):
    """
    Item owner or staff admin confirms manual cash return for a cancelled offline booking.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        try:
            confirmed_booking = confirm_offline_refund(booking, request.user)
        except PermissionDenied as pe:
            return Response({'error': str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as ve:
            return Response(ve.detail, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': 'Offline cash refund confirmed successfully.',
            'booking_id': confirmed_booking.id,
            'payment_status': confirmed_booking.payment_status,
            'refund_status': confirmed_booking.refund_status,
            'cash_returned_at': confirmed_booking.cash_returned_at_display,
            'booking': BookingDetailSerializer(confirmed_booking, context={'request': request}).data
        })


class OwnerApproveBookingView(APIView):
    """
    Item owner approves a pending booking request.
    Moves status from pending_approval to waiting_for_pickup.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can approve this booking request.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'pending_approval':
            return Response(
                {'error': f'Cannot approve booking with current status: {booking.get_status_display()}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        availability = get_item_availability(booking.item, booking.start_date, booking.end_date)
        if booking.requested_quantity > availability['available_stock']:
            return Response(
                {'requested_quantity':
                 f'Requested quantity is unavailable. Only {availability["available_stock"]} items are currently available for these dates.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        booking.status = 'waiting_for_pickup'
        booking.approved_at = timezone.now()
        booking.save(update_fields=['status', 'approved_at', 'updated_at'])
        notify_booking_event(booking, 'accepted')

        return Response({
            'message': 'Booking request approved. Now waiting for pickup.',
            'booking_id': booking.id,
            'status': booking.status
        })


class OwnerRejectBookingView(APIView):
    """
    Item owner declines a pending booking request.
    Moves status from pending_approval to rejected.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can decline this booking request.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'pending_approval':
            return Response(
                {'error': f'Cannot decline booking with current status: {booking.get_status_display()}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', '')
        if not isinstance(reason, str) or not reason.strip():
            return Response(
                {'error': 'A valid rejection reason is required to reject this booking.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        clean_reason = reason.strip()
        booking.status = 'rejected'
        booking.rejected_at = timezone.now()
        booking.rejection_reason = clean_reason
        booking.cancelled_by = request.user
        booking.save(update_fields=['status', 'rejected_at', 'rejection_reason', 'cancelled_by', 'updated_at'])
        notify_booking_event(booking, 'rejected')

        # Notify users who requested availability notifications for this item
        process_availability_notifications_for_item(booking.item_id)

        return Response({
            'message': 'Booking request declined.',
            'booking_id': booking.id,
            'status': booking.status
        })


def verify_and_confirm_pickup(booking, request_user, otp_str):
    """
    Internal transactional helper to verify pickup OTP and confirm pickup handover.
    Can be called by VerifyPickupOtpView and ConfirmPickupView.
    Enforces all permissions, status checks, attempts, expiration, and invalidation rules.
    """
    if booking.owner_id != request_user.id and not request_user.is_staff:
        return Response(
            {'error': 'Only the item owner can verify pickup OTP and confirm item handover.'},
            status=status.HTTP_403_FORBIDDEN
        )

    if booking.status != 'waiting_for_pickup':
        if booking.status in ('rental_in_progress', 'completed'):
            return Response(
                {'error': 'Pickup has already been confirmed for this booking.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            {'error': f'Cannot confirm pickup for booking in "{booking.get_status_display()}" state.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not booking.is_payment_verified():
        return Response(
            {'error': 'Pickup cannot be confirmed until payment is verified by the platform.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if booking.pickup_confirmed_at:
        return Response(
            {'error': 'Pickup has already been confirmed.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    clean_otp = str(otp_str or '').strip()
    if not clean_otp or not clean_otp.isdigit() or len(clean_otp) != 6:
        return Response(
            {'error': 'Please provide a valid 6-digit numeric OTP.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not booking.pickup_otp_hash:
        return Response(
            {'error': 'No active pickup OTP found. Please request a pickup OTP first.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check maximum 5 attempts limit
    if booking.pickup_otp_attempts >= 5:
        booking.pickup_otp_hash = ''
        booking.pickup_otp_expires_at = None
        booking.save(update_fields=['pickup_otp_hash', 'pickup_otp_expires_at', 'updated_at'])
        return Response(
            {'error': 'Too many failed verification attempts. This OTP has been invalidated. Please generate a new OTP.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check expiry (10 minutes)
    if not booking.pickup_otp_expires_at or timezone.now() > booking.pickup_otp_expires_at:
        booking.pickup_otp_hash = ''
        booking.pickup_otp_expires_at = None
        booking.save(update_fields=['pickup_otp_hash', 'pickup_otp_expires_at', 'updated_at'])
        return Response(
            {'error': 'Pickup OTP has expired. Please request a new OTP.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate OTP against stored secure hash
    if not check_password(clean_otp, booking.pickup_otp_hash):
        booking.pickup_otp_attempts += 1
        booking.save(update_fields=['pickup_otp_attempts', 'updated_at'])
        remaining = 5 - booking.pickup_otp_attempts
        if remaining <= 0:
            booking.pickup_otp_hash = ''
            booking.pickup_otp_expires_at = None
            booking.save(update_fields=['pickup_otp_hash', 'pickup_otp_expires_at', 'updated_at'])
            return Response(
                {'error': 'Incorrect OTP. Maximum attempts reached. Please generate a new pickup OTP.', 'attempts_remaining': 0},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            {'error': f'Incorrect OTP. {remaining} attempt(s) remaining.', 'attempts_remaining': remaining},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Successful verification: change status, record server timestamp, invalidate OTP
    now = timezone.now()
    booking.status = 'rental_in_progress'
    booking.pickup_confirmed_at = now
    booking.picked_up_at = now
    booking.pickup_confirmed_by = request_user
    booking.pickup_otp_verified_at = now
    booking.pickup_otp_hash = ''  # Invalidate immediately; single-use only
    booking.pickup_otp_expires_at = None
    booking.pickup_otp_attempts = 0
    booking.save(update_fields=[
        'status', 'pickup_confirmed_at', 'picked_up_at', 'pickup_confirmed_by',
        'pickup_otp_verified_at', 'pickup_otp_hash', 'pickup_otp_expires_at',
        'pickup_otp_attempts', 'updated_at'
    ])

    # Notifications
    try:
        InAppNotification.objects.create(
            user=booking.renter,
            item=booking.item,
            booking=booking,
            title='Pickup Confirmed!',
            message=f"Pickup for '{booking.item.name}' (Booking #{booking.booking_reference}) has been confirmed by the owner. Your rental timer is now running.",
            event='pickup_confirmed'
        )
    except Exception as exc:
        logger.warning(f"Failed to record pickup confirmation notification: {exc}")

    try:
        send_web_push(
            booking.renter,
            title="RentBee - Pickup Confirmed",
            body=f"Your rental for {booking.item.name} is now in progress.",
            data={'url': f"/bookings/{booking.id}", 'booking_id': booking.id, 'event': 'pickup_confirmed'}
        )
    except Exception as exc:
        logger.warning(f"Web push dispatch failed on pickup confirmation: {exc}")

    return Response({
        'message': 'Pickup confirmed successfully! Rental is now in progress.',
        'booking_id': booking.id,
        'status': booking.status,
        'pickup_confirmed_at': booking.pickup_confirmed_at_display,
    }, status=status.HTTP_200_OK)


class SendPickupOtpView(APIView):
    """
    Item owner initiates pickup verification.
    Generates a cryptographically secure 6-digit OTP and dispatches it
    to the renter's registered mobile number via configured SMS provider.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can generate and send pickup OTP.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'waiting_for_pickup':
            if booking.status in ('rental_in_progress', 'completed'):
                return Response(
                    {'error': 'Pickup has already been confirmed for this booking.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if booking.status == 'pending_approval':
                return Response(
                    {'error': 'Cannot send pickup OTP. Booking request is pending owner approval.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if booking.status == 'rejected':
                return Response(
                    {'error': 'Cannot send pickup OTP for a declined booking.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if booking.status == 'cancelled':
                return Response(
                    {'error': 'Cannot send pickup OTP for a cancelled booking.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if booking.status == 'expired':
                return Response(
                    {'error': 'Cannot send pickup OTP for an expired booking.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response(
                {'error': f'Cannot send pickup OTP for booking in "{booking.get_status_display()}" state.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not booking.is_payment_verified():
            return Response(
                {'error': 'Pickup OTP cannot be generated until payment is verified by the platform.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if booking.pickup_confirmed_at:
            return Response(
                {'error': 'Pickup has already been confirmed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 60-second Resend Cooldown
        if booking.pickup_otp_created_at:
            cooldown_period = timedelta(seconds=60)
            elapsed = timezone.now() - booking.pickup_otp_created_at
            if elapsed < cooldown_period:
                remaining_seconds = int((cooldown_period - elapsed).total_seconds())
                return Response(
                    {
                        'error': f'Please wait {remaining_seconds} second(s) before requesting a new OTP.',
                        'cooldown_seconds': remaining_seconds
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

        renter_phone = getattr(booking.renter, 'phone_number', None)
        if not renter_phone:
            return Response(
                {'error': 'Renter does not have a registered mobile number for OTP delivery.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Cryptographically secure random 6-digit OTP using secrets module
        otp = f"{secrets.randbelow(1_000_000):06d}"
        now = timezone.now()

        # Resending invalidates previous OTP: overwrite hash and reset attempts
        booking.pickup_otp_hash = make_password(otp)
        booking.pickup_otp_expires_at = now + timedelta(minutes=10)
        booking.pickup_otp_created_at = now
        booking.pickup_otp_attempts = 0
        booking.save(update_fields=[
            'pickup_otp_hash', 'pickup_otp_expires_at', 'pickup_otp_created_at',
            'pickup_otp_attempts', 'updated_at'
        ])

        # Dispatch through SMS service
        try:
            sms_res = send_pickup_otp_sms(booking, otp)
        except SMSConfigurationError as exc:
            return Response(
                {'error': f'SMS service configuration error: {exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except SMSSendError as exc:
            return Response(
                {'error': f'Failed to send SMS to renter: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as exc:
            logger.error("Unexpected error dispatching pickup OTP SMS: %s", exc)
            return Response(
                {'error': 'An unexpected error occurred while dispatching the pickup OTP SMS.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({
            'message': f"Pickup OTP sent successfully to renter ({sms_res.get('masked_phone')}).",
            'masked_phone': sms_res.get('masked_phone'),
            'expires_in_minutes': 10,
            'resend_cooldown_seconds': 60,
        }, status=status.HTTP_200_OK)


class VerifyPickupOtpView(APIView):
    """
    Item owner enters the 6-digit OTP received by renter.
    Validates OTP and confirms item handover.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        otp = request.data.get('otp', '')
        return verify_and_confirm_pickup(booking, request.user, otp)


class ConfirmPickupView(APIView):
    """
    Item owner confirms handover of the item to renter.
    Requires OTP verification to prevent bypassing pickup security.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        otp = request.data.get('otp', '')
        if not otp:
            return Response(
                {'error': 'Pickup confirmation requires OTP verification. Please provide the 6-digit OTP sent to the renter.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return verify_and_confirm_pickup(booking, request.user, otp)


class ConfirmReturnView(APIView):
    """
    Item owner confirms physical return of the item.
    Moves status from rental_in_progress to completed.
    Never triggers automatically.
    """
    permission_classes = [IsAuthenticated]

    @locked_booking_transition
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.owner_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the item owner can confirm item return.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'rental_in_progress':
            return Response(
                {'error': f'Cannot confirm return for booking in "{booking.get_status_display()}" state.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        booking.status = 'completed'
        booking.returned_at = timezone.now()
        booking.save(update_fields=['status', 'returned_at', 'updated_at'])
        process_availability_notifications_for_item(booking.item_id)

        return Response({
            'message': 'Rental completed successfully.',
            'booking_id': booking.id,
            'status': booking.status
        })


class CreatePaymentOrderView(APIView):
    """
    Creates or reuses a Razorpay order for an approved rental booking.
    Strictly restricted to the booking's authenticated renter.
    Requires booking to be in 'waiting_for_pickup' status.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        with transaction.atomic():
            booking = get_object_or_404(Booking.objects.select_for_update(), pk=pk)

            if booking.renter_id != request.user.id and not request.user.is_staff:
                return Response(
                    {'error': 'Only the booking renter can initiate payment.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if booking.status != 'waiting_for_pickup':
                if booking.status == 'pending_approval':
                    return Response(
                        {'error': 'Payment can only be initiated after the owner accepts the booking request.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                return Response(
                    {'error': f'Payment cannot be initiated for {booking.get_status_display()} bookings.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if booking.payment_status == 'paid':
                return Response(
                    {'error': 'This booking has already been paid and verified.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if getattr(booking, 'payment_method', 'online') == 'offline':
                return Response(
                    {'error': 'Online payment order cannot be created for offline Pay at Pickup bookings.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            order_data = get_or_create_razorpay_order_for_booking(booking)

            prefill = {
                'name': request.user.get_full_name() or request.user.username or '',
                'email': request.user.email or '',
                'contact': getattr(request.user, 'phone_number', '') or '',
            }

            return Response({
                **order_data,
                'booking_reference': booking.booking_reference,
                'item_name': booking.item.name,
                'prefill': prefill,
            }, status=status.HTTP_200_OK)


class VerifyPaymentView(APIView):
    """
    Verifies Razorpay payment signature and confirms captured status.
    Idempotent and concurrency-safe. Updates booking payment_status to 'paid'.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = PaymentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data['razorpay_order_id']
        payment_id = serializer.validated_data['razorpay_payment_id']
        signature = serializer.validated_data['razorpay_signature']

        with transaction.atomic():
            booking = get_object_or_404(Booking.objects.select_for_update(), pk=pk)

            if booking.renter_id != request.user.id and not request.user.is_staff:
                return Response(
                    {'error': 'Only the booking renter or staff can verify payment.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if booking.status != 'waiting_for_pickup':
                return Response(
                    {'error': f'Payment verification cannot be performed for {booking.get_status_display()} bookings.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if booking.payment_status == 'paid' and booking.payment_transaction_id != payment_id:
                return Response(
                    {'error': 'This booking has already been paid and verified.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if getattr(booking, 'payment_method', 'online') == 'offline':
                return Response(
                    {'error': 'Online payment verification cannot be performed for offline Pay at Pickup bookings.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            verify_razorpay_payment(
                booking=booking,
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=signature
            )

            detail_serializer = BookingDetailSerializer(booking, context={'request': request})
            return Response({
                'message': 'Payment verified successfully.',
                'booking': detail_serializer.data,
            }, status=status.HTTP_200_OK)


class ConfirmOfflinePaymentView(APIView):
    """
    Host or admin confirms cash receipt for an offline (Pay at Pickup) booking.
    Updates payment_status to 'paid' and records payment_verified_at and payment_verified_by.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        try:
            confirmed_booking = confirm_offline_booking_payment(booking, request.user)
        except PermissionDenied as e:
            msg = e.detail if hasattr(e, 'detail') else str(e)
            return Response({'error': msg}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as e:
            msg = e.detail if hasattr(e, 'detail') else str(e)
            if isinstance(msg, dict) and 'error' in msg:
                msg = msg['error']
            elif isinstance(msg, list) and len(msg) == 1:
                msg = msg[0]
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

        serializer = BookingDetailSerializer(confirmed_booking, context={'request': request})
        return Response({
            'message': 'Offline payment confirmed successfully.',
            'booking': serializer.data,
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(APIView):
    """
    Receives and processes asynchronous webhook events from Razorpay.
    Self-authenticates using HMAC-SHA256 signature and RAZORPAY_WEBHOOK_SECRET.
    Tracks processed event IDs in ProcessedWebhookEvent to prevent duplicates.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        signature = request.headers.get('X-Razorpay-Signature', '') or request.META.get('HTTP_X_RAZORPAY_SIGNATURE', '')
        if not signature:
            return Response({'error': 'Missing X-Razorpay-Signature header.'}, status=status.HTTP_400_BAD_REQUEST)

        raw_body = request.body
        is_valid = verify_webhook_signature(raw_body, signature)
        if not is_valid:
            return Response({'error': 'Invalid webhook signature.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            event_data = json.loads(raw_body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return Response({'error': 'Invalid JSON payload.'}, status=status.HTTP_400_BAD_REQUEST)

        result = process_razorpay_webhook_event(event_data)
        return Response(result, status=status.HTTP_200_OK)


class ReportProblemView(APIView):
    """
    Renter reports an issue with their rental.
    Strictly restricted to rental_in_progress only.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)

        if booking.renter_id != request.user.id and not request.user.is_staff:
            return Response(
                {'error': 'Only the renter can report a problem for this booking.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != 'rental_in_progress':
            return Response(
                {'error': 'Problem reports can only be submitted while a rental is in progress.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        description = request.data.get('description', '').strip()
        if not description:
            return Response(
                {'description': ['Problem description is required.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        report = IssueReport.objects.create(
            booking=booking,
            renter=request.user,
            owner=booking.owner,
            description=description,
            status='open'
        )

        serializer = IssueReportSerializer(report, context={'request': request})
        return Response({
            'message': 'Problem reported successfully. The owner and platform support have been notified.',
            'report': serializer.data
        }, status=status.HTTP_201_CREATED)


class HostBookingsListView(APIView):
    """
    Owner's Host Hub endpoint for incoming requests and active rentals.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        expire_stale_pending_bookings()

        user = request.user
        base_qs = Booking.objects.filter(owner=user).select_related(
            'item', 'item__category', 'renter'
        ).prefetch_related('item__images')

        tab = request.query_params.get('tab', 'all').lower()
        if tab == 'incoming':
            qs = base_qs.filter(status='pending_approval')
        elif tab in ['accepted', 'active']:
            qs = base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress'])
        elif tab == 'rejected':
            qs = base_qs.filter(status='rejected')
        elif tab == 'completed':
            qs = base_qs.filter(status='completed')
        else:
            qs = base_qs

        counts = {
            'all': base_qs.count(),
            'incoming': base_qs.filter(status='pending_approval').count(),
            'accepted': base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress']).count(),
            'active': base_qs.filter(status__in=['waiting_for_pickup', 'rental_in_progress']).count(),
            'rejected': base_qs.filter(status='rejected').count(),
            'completed': base_qs.filter(status='completed').count(),
        }

        serializer = BookingListSerializer(qs, many=True, context={'request': request})
        return Response({
            'counts': counts,
            'results': serializer.data
        })


class HostReportsListView(APIView):
    """
    Endpoint for viewing issues reported on user's bookings (as host or renter).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        reports = IssueReport.objects.filter(
            Q(owner=user) | Q(renter=user)
        ).select_related(
            'booking', 'booking__item', 'renter', 'owner'
        ).distinct()
        serializer = IssueReportSerializer(reports, many=True, context={'request': request})
        return Response(serializer.data)


class CheckAvailabilityView(APIView):
    """
    Real-time check whether an item is available for a given date range.
    Returns { is_available, status_label, message, conflicting_count }.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        expire_stale_pending_bookings()

        item_id = request.query_params.get('item_id')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not item_id:
            return Response({'error': 'item_id query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not start_date_str or not end_date_str:
            return Response({'error': 'start_date and end_date query parameters are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid item_id.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Expected YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        if start_date < today:
            return Response({
                'is_available': False,
                'status_label': 'Past Date',
                'message': 'Rental start date cannot be in the past.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if end_date <= start_date:
            return Response({
                'is_available': False,
                'status_label': 'Invalid Dates',
                'message': 'End date must be after start date.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Item.objects.get(pk=item_id)
        except Item.DoesNotExist:
            return Response({'error': 'Item not found.'}, status=status.HTTP_404_NOT_FOUND)

        availability = get_item_availability(item, start_date, end_date)
        requested_quantity = request.query_params.get('requested_quantity')
        requested_quantity_available = None
        if requested_quantity is not None:
            try:
                requested_quantity = int(requested_quantity)
                if requested_quantity < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': 'requested_quantity must be a positive integer.'}, status=status.HTTP_400_BAD_REQUEST)
            requested_quantity_available = requested_quantity <= availability['available_stock']
        message = (
            'Item is available for these dates.' if availability['is_available']
            else 'This item is already booked, reserved, or out of stock for the selected dates.'
        )
        if requested_quantity is not None and not requested_quantity_available:
            message = f'Requested quantity is unavailable. Only {availability["available_stock"]} items are currently available for these dates.'
        return Response({
            **availability,
            'status_label': ('Available' if availability['is_available'] else
                             'Booked' if availability['availability_reason'] == 'reserved' else 'Unavailable'),
            'message': message,
            'conflicting_count': max(0, availability['total_stock'] - availability['available_stock']),
            **({'requested_quantity': requested_quantity,
                'is_requested_quantity_available': requested_quantity_available}
               if requested_quantity is not None else {}),
        })


class NotifyAvailabilityView(APIView):
    """
    Renter requests to be notified if an item becomes available for given dates.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_id = request.data.get('item_id')
        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')

        if not item_id or not start_date_str or not end_date_str:
            return Response({'error': 'item_id, start_date, and end_date are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item_id = int(item_id)
            start_date = timezone.datetime.strptime(str(start_date_str), '%Y-%m-%d').date()
            end_date = timezone.datetime.strptime(str(end_date_str), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response({'error': 'Invalid item_id or date format (expected YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        if start_date < today:
            return Response({'error': 'Rental start date cannot be in the past.'}, status=status.HTTP_400_BAD_REQUEST)

        if end_date <= start_date:
            return Response({'error': 'End date must be after start date.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Item.objects.get(pk=item_id)
        except Item.DoesNotExist:
            return Response({'error': 'Item not found.'}, status=status.HTTP_404_NOT_FOUND)

        req_obj, created = AvailabilityNotificationRequest.objects.get_or_create(
            user=request.user,
            item=item,
            start_date=start_date,
            end_date=end_date,
            defaults={'is_notified': False}
        )
        if not created and req_obj.is_notified:
            req_obj.is_notified = False
            req_obj.save(update_fields=['is_notified'])

        return Response({
            'message': 'You will be notified as soon as these dates become available.',
            'id': req_obj.id,
            'item_id': item.id,
            'item_name': item.name,
            'start_date': str(start_date),
            'end_date': str(end_date),
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class NotificationsListView(APIView):
    """
    List in-app notifications for the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = InAppNotification.objects.filter(user=request.user).select_related('booking__item', 'item').order_by('-created_at')
        unread_count = InAppNotification.objects.filter(user=request.user, is_read=False).count()
        serializer = InAppNotificationSerializer(notifications, many=True, context={'request': request})
        return Response({
            'unread_count': unread_count,
            'results': serializer.data
        })


class MarkNotificationReadView(APIView):
    """
    Mark a specific notification as read.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(InAppNotification, pk=pk, user=request.user)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({
            'message': 'Notification marked as read.',
            'id': notification.id
        })


class MarkAllNotificationsReadView(APIView):
    """
    Mark all notifications as read for the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        InAppNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})


class PushVapidKeyView(APIView):
    """
    Returns the VAPID public key for web push subscription.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'public_key': get_vapid_public_key()})


class PushSubscribeView(APIView):
    """
    Saves or updates a Web Push subscription for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        endpoint = request.data.get('endpoint', '').strip()
        keys = request.data.get('keys', {})
        p256dh = keys.get('p256dh', '').strip() if isinstance(keys, dict) else ''
        auth = keys.get('auth', '').strip() if isinstance(keys, dict) else ''

        if not endpoint or not p256dh or not auth:
            return Response(
                {'error': 'Invalid subscription data. endpoint, keys.p256dh and keys.auth are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        sub, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={
                'p256dh': p256dh,
                'auth': auth,
                'user_agent': user_agent,
            }
        )

        return Response({
            'message': 'Push subscription saved successfully.',
            'created': created,
            'id': sub.id
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PushUnsubscribeView(APIView):
    """
    Removes a Web Push subscription for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        endpoint = request.data.get('endpoint', '').strip()
        if endpoint:
            PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        else:
            PushSubscription.objects.filter(user=request.user).delete()

        return Response({'message': 'Push subscription removed successfully.'})


class PushTestView(APIView):
    """
    Sends a test web push notification to the authenticated user's registered devices.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = send_web_push(
            request.user,
            title='RentBee Test',
            body='Web push notification is working successfully!',
            data={'url': '/host-hub', 'type': 'test'}
        )
        return Response({
            'message': f'Test push notification dispatched to {count} active device(s).',
            'devices_notified': count
        })


class BookingInvoiceView(APIView):
    """
    Generates and downloads a verified PDF Tax Invoice & Payment Receipt.
    Strictly authorized to the booking customer (renter) or staff administrator.
    Requires confirmed payment (payment_status == 'paid').
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            booking = (
                Booking.objects
                .select_related('item', 'item__category', 'renter', 'owner', 'payment_verified_by')
                .get(pk=pk)
            )
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        # 1. Authorization: Only the authenticated customer (renter) or staff admin
        is_customer = (request.user.id == booking.renter_id)
        is_admin = (request.user.is_staff or request.user.is_superuser)
        if not (is_customer or is_admin):
            return Response(
                {'error': 'You are not authorized to download this customer invoice/receipt.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Payment Verification: Must be verified paid
        if booking.payment_status != 'paid':
            return Response(
                {'error': 'Invoice and receipt are only available for confirmed payments.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Generate PDF using immutable booking snapshots
        try:
            from .pdf_service import generate_booking_invoice_pdf
            pdf_bytes = generate_booking_invoice_pdf(booking)
        except Exception as e:
            return Response(
                {'error': f'Failed to generate invoice PDF: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 4. Stream PDF Response as downloadable attachment
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"RentBee_Invoice_{booking.booking_reference}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = len(pdf_bytes)
        return response


class DiscountEligibilityView(APIView):
    """
    Checks if the requesting user is eligible for the First Booking 10% discount.
    Returns discount details if eligible, or eligibility status false if ineligible / unauthenticated.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return Response({
                'is_eligible': False,
                'discount_percentage': 10,
                'discount_type': 'FIRST_BOOKING_10',
                'title': 'First Booking 10% Discount',
                'description': 'Sign up or log in to get 10% discount on your first booking!'
            }, status=status.HTTP_200_OK)

        eligible = is_user_eligible_for_first_booking_discount(user)
        return Response({
            'is_eligible': eligible,
            'discount_percentage': 10 if eligible else 0,
            'discount_type': 'FIRST_BOOKING_10' if eligible else '',
            'title': 'First Booking 10% Discount',
            'description': '10% discount applied automatically on your first rental!' if eligible else 'Offer already redeemed or active.'
        }, status=status.HTTP_200_OK)





