from datetime import timedelta
from decimal import Decimal
import logging
import hmac
import hashlib
import uuid
import razorpay
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from functools import wraps
from rest_framework.exceptions import ValidationError, PermissionDenied
from catalog.models import Item
from django.utils import timezone
from .models import Booking, AvailabilityNotificationRequest, InAppNotification, ProcessedWebhookEvent

logger = logging.getLogger(__name__)


def process_availability_notifications_for_item(item_id):
    """
    Checks unfulfilled availability notification requests for the given item.
    If the requested date range has no active conflicts, creates an InAppNotification
    for the user and marks the request as notified (avoiding duplicate notifications).
    """
    pending_reqs = AvailabilityNotificationRequest.objects.filter(
        item_id=item_id,
        is_notified=False
    ).select_related('item', 'user')

    for req in pending_reqs:
        # Check if dates are now free of conflicts
        availability = get_item_availability(req.item, req.start_date, req.end_date)
        if availability['is_available']:
            InAppNotification.objects.create(
                user=req.user,
                title="Dates Now Available!",
                message=(
                    f"Good news! '{req.item.name}' is now available for your requested dates "
                    f"({req.start_date} to {req.end_date}). Book now before it's taken!"
                ),
                item=req.item
            )
            req.is_notified = True
            req.notified_at = timezone.now()
            req.save(update_fields=['is_notified', 'notified_at'])


def expire_stale_pending_bookings():
    """
    Opportunistic/deterministic expiry helper.
    Finds any 'pending_approval' booking older than RENTAL_PENDING_APPROVAL_EXPIRY_HOURS
    and transitions its status to 'expired'.
    Can be called before availability queries and dashboard listings to guarantee accurate state
    even without background cron tasks.
    """
    expiry_hours = getattr(settings, 'RENTAL_PENDING_APPROVAL_EXPIRY_HOURS', 24)
    cutoff = timezone.now() - timedelta(hours=expiry_hours)
    
    item_ids = Booking.objects.filter(
        status='pending_approval', created_at__lt=cutoff
    ).values_list('item_id', flat=True).distinct()
    count = 0
    for item_id in sorted(item_ids):
        with transaction.atomic():
            Item.objects.select_for_update().get(pk=item_id)
            stale = list(Booking.objects.select_for_update().filter(
                item_id=item_id, status='pending_approval', created_at__lt=cutoff
            ).values_list('pk', flat=True))
            if stale:
                count += Booking.objects.filter(pk__in=stale).update(
                    status='expired', updated_at=timezone.now())
                transaction.on_commit(
                    lambda item_id=item_id: process_availability_notifications_for_item(item_id))
    return count


def locked_booking_transition(action):
    """Serialize status decisions: always lock item before booking."""
    @wraps(action)
    def wrapped(view, request, pk, *args, **kwargs):
        expire_stale_pending_bookings()
        item_id = get_object_or_404(Booking, pk=pk).item_id
        with transaction.atomic():
            get_object_or_404(Item.objects.select_for_update(), pk=item_id)
            booking = get_object_or_404(Booking.objects.select_for_update(), pk=pk, item_id=item_id)
            if booking.is_expired_pending():
                booking.status = 'expired'
                booking.save(update_fields=['status', 'updated_at'])
                transaction.on_commit(
                    lambda: process_availability_notifications_for_item(item_id))
            return action(view, request, pk, *args, **kwargs)
    return wrapped


def get_next_available_date(item):
    """Earliest free inclusive day, not a promise for a multi-day rental."""
    today = timezone.localdate()
    if item.stock <= 0 or Booking.objects.filter(item=item, status='rental_in_progress').exists():
        return None
    candidates = {today}
    for end in Booking.objects.filter(
        item=item, status='waiting_for_pickup',
        end_date__gte=today
    ).values_list('end_date', flat=True):
        candidates.add(end + timedelta(days=1))
    for day in sorted(candidates):
        if get_item_availability(item, day, day)['is_available']:
            return day.isoformat()
    return None


def mark_booking_payment_verified(booking, verified_by=None, transaction_id=''):
    """
    Authorized backend payment verification service.
    Exclusively invoked by staff admin action, backend CLI, or payment gateway verification.
    """
    booking.payment_status = 'paid'
    booking.payment_verified_at = timezone.now()
    if verified_by and verified_by.is_authenticated:
        booking.payment_verified_by = verified_by
    if transaction_id:
        booking.payment_transaction_id = transaction_id
    booking.save(update_fields=[
        'payment_status',
        'payment_verified_at',
        'payment_verified_by',
        'payment_transaction_id',
        'updated_at'
    ])
    return booking


def is_user_eligible_for_first_booking_discount(user):
    """
    Evaluates whether a registered user is eligible for the 10% First Booking discount.
    Rules:
    1. Must be an authenticated, registered user.
    2. Must NOT have any prior successful booking:
       - approved_at is not None
       - payment_verified_at is not None
       - payment_status == 'paid'
       - status in ['waiting_for_pickup', 'rental_in_progress', 'completed']
    3. Must NOT have any active, in-flight booking currently holding the discount
       (status == 'pending_approval' with discount_amount > 0).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    # Check for any prior successful booking (approved, paid, active, or completed)
    has_successful_booking = Booking.objects.filter(renter=user).filter(
        Q(status__in=['waiting_for_pickup', 'rental_in_progress', 'completed']) |
        Q(payment_status='paid') |
        Q(approved_at__isnull=False) |
        Q(payment_verified_at__isnull=False)
    ).exists()

    if has_successful_booking:
        return False

    # Check for in-flight pending bookings holding the discount
    has_active_discount_booking = Booking.objects.filter(
        renter=user,
        status='pending_approval',
        discount_amount__gt=0
    ).exists()

    if has_active_discount_booking:
        return False

    return True


def get_razorpay_client():
    """Returns an authenticated Razorpay Client using configured settings."""
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not key_id or not key_secret:
        raise ValidationError({'error': 'Razorpay payment gateway credentials are not configured on the server.'})
    return razorpay.Client(auth=(key_id, key_secret))


def get_or_create_razorpay_order_for_booking(booking):
    """
    Creates or reuses an existing Razorpay order for an approved booking.
    Safety guarantees:
    - Only allowed when booking status is 'waiting_for_pickup'.
    - Existing orders are reused if still valid and payable.
    - If the previous order has expired, was cancelled, or fails validation, creates a new order.
    """
    if booking.status != 'waiting_for_pickup':
        if booking.status == 'pending_approval':
            raise ValidationError({'error': 'Payment can only be initiated after the owner accepts the booking request.'})
        raise ValidationError({'error': f'Payment cannot be initiated for {booking.get_status_display()} bookings.'})

    if booking.payment_status == 'paid':
        raise ValidationError({'error': 'Payment for this booking has already been verified.'})

    if getattr(booking, 'payment_method', 'online') == 'offline':
        raise ValidationError({'error': 'Online payment order cannot be created for offline Pay at Pickup bookings.'})

    expected_amount_paise = int(round(booking.total_amount * 100))
    if expected_amount_paise <= 0:
        raise ValidationError({'error': 'Invalid booking total amount.'})

    client = get_razorpay_client()

    # Attempt to reuse existing order if still valid & payable
    if booking.razorpay_order_id:
        try:
            existing_order = client.order.fetch(booking.razorpay_order_id)
            order_status = existing_order.get('status')
            order_amount = existing_order.get('amount')
            order_paid = existing_order.get('amount_paid', 0)
            order_currency = existing_order.get('currency', 'INR')

            # Reusable if: status is 'created' or 'attempted', amount matches, currency is INR, and not yet paid
            if order_status in ['created', 'attempted'] and order_amount == expected_amount_paise and order_currency == 'INR' and order_paid < order_amount:
                return {
                    'order_id': existing_order['id'],
                    'amount': existing_order['amount'],
                    'currency': existing_order['currency'],
                    'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
                    'is_reused': True,
                }
            elif order_status == 'paid' or order_paid >= order_amount:
                return {
                    'order_id': existing_order['id'],
                    'amount': existing_order['amount'],
                    'currency': existing_order['currency'],
                    'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
                    'is_reused': True,
                    'is_already_paid': True,
                }
        except Exception as e:
            logger.warning(f"Could not reuse Razorpay order {booking.razorpay_order_id}: {e}. Creating new order.")

    # Create new Razorpay order
    receipt = f"bk_{booking.id}_{uuid.uuid4().hex[:8]}"[:40]
    order_data = {
        'amount': expected_amount_paise,
        'currency': 'INR',
        'receipt': receipt,
        'notes': {
            'booking_id': str(booking.id),
            'booking_reference': booking.booking_reference,
            'renter_id': str(booking.renter_id),
            'item_id': str(booking.item_id),
            'discount_amount': str(booking.discount_amount),
            'discount_type': booking.discount_type or 'NONE',
            'original_rental_amount': str(booking.original_rental_amount or booking.rental_amount),
        }
    }
    new_order = client.order.create(data=order_data)
    booking.razorpay_order_id = new_order['id']
    booking.save(update_fields=['razorpay_order_id', 'updated_at'])

    return {
        'order_id': new_order['id'],
        'amount': new_order['amount'],
        'currency': new_order['currency'],
        'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        'is_reused': False,
    }


def verify_razorpay_payment(booking, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verifies Razorpay payment signature AND confirms the payment is captured.
    Guarantees idempotency and concurrency safety.
    """
    if getattr(booking, 'payment_method', 'online') == 'offline':
        raise ValidationError({'error': 'Online payment verification cannot be performed for offline Pay at Pickup bookings.'})

    if booking.status != 'waiting_for_pickup':
        raise ValidationError({'error': f'Payment verification cannot be performed for {booking.get_status_display()} bookings.'})

    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        raise ValidationError({'error': 'razorpay_order_id, razorpay_payment_id, and razorpay_signature are required.'})

    # Order ID match check
    if booking.razorpay_order_id and booking.razorpay_order_id != razorpay_order_id:
        raise ValidationError({'error': f'Order ID mismatch: expected {booking.razorpay_order_id}, got {razorpay_order_id}'})

    # Cryptographic HMAC SHA-256 signature verification
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not key_secret:
        raise ValidationError({'error': 'Razorpay key secret is not configured on the server.'})

    msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8')
    expected_sig = hmac.new(key_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_sig, razorpay_signature):
        raise ValidationError({'error': 'Invalid payment signature. Payment verification failed.'})

    # Requirement 1: Confirm the payment has been successfully captured in Razorpay
    client = get_razorpay_client()
    try:
        payment = client.payment.fetch(razorpay_payment_id)
    except Exception as e:
        logger.error(f"Failed to fetch payment details for {razorpay_payment_id}: {e}")
        raise ValidationError({'error': f'Failed to retrieve payment confirmation from Razorpay: {str(e)}'})

    payment_status = payment.get('status')
    if payment_status != 'captured':
        raise ValidationError({'error': f'Payment must be captured before verification. Current status: {payment_status}'})

    expected_amount_paise = int(round(booking.total_amount * 100))
    if payment.get('amount') != expected_amount_paise:
        raise ValidationError({'error': f'Amount mismatch: expected {expected_amount_paise} paise, got {payment.get("amount")}'})

    if payment.get('currency') != 'INR':
        raise ValidationError({'error': f'Currency mismatch: expected INR, got {payment.get("currency")}'})

    if payment.get('order_id') != razorpay_order_id:
        raise ValidationError({'error': f'Order ID mismatch on payment record: expected {razorpay_order_id}, got {payment.get("order_id")}'})

    # Prevent crediting the same payment ID to multiple bookings
    other_booking = Booking.objects.filter(payment_transaction_id=razorpay_payment_id).exclude(pk=booking.pk).first()
    if other_booking:
        raise ValidationError({'error': f'Payment {razorpay_payment_id} has already been credited to booking #{other_booking.booking_reference}.'})

    # Idempotency check on this booking
    if booking.payment_status == 'paid':
        if booking.payment_transaction_id == razorpay_payment_id:
            return booking
        else:
            raise ValidationError({'error': f'Booking is already marked as paid with transaction {booking.payment_transaction_id}.'})

    # Update payment status
    mark_booking_payment_verified(booking, transaction_id=razorpay_payment_id)

    # Post-commit notification guarantee
    transaction.on_commit(lambda: notify_payment_verified(booking))

    return booking


def verify_webhook_signature(raw_body, signature):
    """Verifies Razorpay webhook payload signature using RAZORPAY_WEBHOOK_SECRET."""
    webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    if not webhook_secret:
        raise ValidationError({'error': 'Razorpay webhook secret is not configured.'})

    body_bytes = raw_body if isinstance(raw_body, bytes) else raw_body.encode('utf-8')
    expected_sig = hmac.new(webhook_secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


def process_razorpay_webhook_event(event_data):
    """
    Idempotent processor for verified Razorpay webhook events.
    Tracks processed event IDs in ProcessedWebhookEvent to prevent duplicate executions.
    """
    event_id = event_data.get('event_id') or event_data.get('id', '')
    event_type = event_data.get('event', '')

    if not event_id:
        return {'status': 'ignored', 'reason': 'Missing event ID'}

    with transaction.atomic():
        if ProcessedWebhookEvent.objects.filter(event_id=event_id).exists():
            return {'status': 'already_processed', 'event_id': event_id}

        if event_type in ['payment.captured', 'order.paid']:
            payment_entity = (
                event_data.get('payload', {}).get('payment', {}).get('entity', {})
                if 'payment' in event_data.get('payload', {})
                else {}
            )
            order_id = payment_entity.get('order_id') or event_data.get('payload', {}).get('order', {}).get('entity', {}).get('id')
            payment_id = payment_entity.get('id', '')
            amount = payment_entity.get('amount')
            currency = payment_entity.get('currency', 'INR')
            payment_status = payment_entity.get('status', '')

            if not order_id:
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'ignored', 'reason': 'No order_id in event payload'}

            booking = Booking.objects.select_for_update().filter(razorpay_order_id=order_id).first()
            if not booking:
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'ignored', 'reason': f'No booking found for order {order_id}'}

            if getattr(booking, 'payment_method', 'online') == 'offline':
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'ignored', 'reason': 'Booking payment method is offline'}

            if payment_status and payment_status != 'captured':
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'ignored', 'reason': f'Payment status is {payment_status}, not captured'}

            expected_amount_paise = int(round(booking.total_amount * 100))
            if amount and amount != expected_amount_paise:
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'error', 'reason': f'Amount mismatch: expected {expected_amount_paise}, got {amount}'}

            if currency and currency != 'INR':
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'error', 'reason': f'Currency mismatch: expected INR, got {currency}'}

            if booking.payment_status != 'paid':
                txn_id = payment_id or booking.payment_transaction_id or f"WH-{event_id}"
                mark_booking_payment_verified(booking, transaction_id=txn_id)
                transaction.on_commit(lambda: notify_payment_verified(booking))

            ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
            return {'status': 'success', 'booking_id': booking.id}

        elif event_type == 'payment.failed':
            payment_entity = event_data.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = payment_entity.get('order_id')
            if order_id:
                booking = Booking.objects.select_for_update().filter(razorpay_order_id=order_id).first()
                if booking and getattr(booking, 'payment_method', 'online') == 'offline':
                    ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                    return {'status': 'ignored', 'reason': 'Booking payment method is offline'}
                if booking and booking.payment_status == 'pending':
                    booking.payment_status = 'failed'
                    booking.save(update_fields=['payment_status', 'updated_at'])

            ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
            return {'status': 'failure_recorded', 'event_id': event_id}

        elif event_type in ['refund.created', 'refund.processed', 'refund.failed']:
            refund_entity = (
                event_data.get('payload', {}).get('refund', {}).get('entity', {})
                if 'refund' in event_data.get('payload', {})
                else {}
            )
            refund_id = refund_entity.get('id', '')
            payment_id = refund_entity.get('payment_id', '')
            refund_amount_paise = refund_entity.get('amount')
            notes = refund_entity.get('notes', {}) or {}
            booking_id = notes.get('booking_id')
            booking_reference = notes.get('booking_reference')

            # Match booking using refund ID, payment ID, or notes
            booking = None
            if refund_id:
                booking = Booking.objects.select_for_update().filter(refund_transaction_id=refund_id).first()
            if not booking and payment_id:
                booking = Booking.objects.select_for_update().filter(payment_transaction_id=payment_id).first()
            if not booking and booking_id:
                try:
                    booking = Booking.objects.select_for_update().filter(id=int(booking_id)).first()
                except (ValueError, TypeError):
                    pass
            if not booking and booking_reference:
                booking = Booking.objects.select_for_update().filter(booking_reference=booking_reference).first()

            if not booking:
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'ignored', 'reason': f'No booking found for refund {refund_id} / payment {payment_id}'}

            if getattr(booking, 'payment_method', 'online') == 'offline':
                ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
                return {'status': 'ignored', 'reason': 'Booking payment method is offline'}

            # Store refund reference and amount if not already present
            if refund_id and not booking.refund_transaction_id:
                booking.refund_transaction_id = refund_id
            if refund_amount_paise and not booking.refund_amount:
                booking.refund_amount = Decimal(refund_amount_paise) / Decimal(100)

            if event_type == 'refund.processed':
                booking.refund_status = 'processed'
                booking.payment_status = 'refunded'
                if not booking.refunded_at:
                    booking.refunded_at = timezone.now()
                booking.save(update_fields=[
                    'refund_transaction_id', 'refund_amount', 'refund_status',
                    'payment_status', 'refunded_at', 'updated_at'
                ])
                transaction.on_commit(lambda: notify_refund_processed(booking))

            elif event_type == 'refund.failed':
                booking.refund_status = 'failed'
                # Keep original payment_status as 'paid'
                if booking.payment_status == 'refunded':
                    booking.payment_status = 'paid'
                booking.save(update_fields=[
                    'refund_transaction_id', 'refund_amount', 'refund_status',
                    'payment_status', 'updated_at'
                ])

            elif event_type == 'refund.created':
                if booking.refund_status != 'processed':
                    booking.refund_status = 'pending'
                    # payment_status must remain 'paid' while refund is pending
                    booking.save(update_fields=[
                        'refund_transaction_id', 'refund_amount', 'refund_status', 'updated_at'
                    ])

            ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
            return {'status': 'success', 'booking_id': booking.id, 'refund_event': event_type}

        else:
            ProcessedWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
            return {'status': 'ignored', 'event_type': event_type}


def notify_payment_verified(booking):
    """
    Sends in-app and web push notifications to the host and renter upon payment verification.
    """
    # 1. Notify host
    owner = booking.owner
    owner_title = "Payment Received!"
    owner_message = (
        f"Payment of ₹{booking.total_amount} for booking #{booking.booking_reference} "
        f"({booking.item.name}) has been verified. You may now confirm item handover/pickup."
    )
    InAppNotification.objects.get_or_create(
        user=owner,
        booking=booking,
        event='payment_verified_owner',
        defaults={'item': booking.item, 'title': owner_title, 'message': owner_message}
    )
    try:
        from .push_service import send_web_push
        send_web_push(
            owner,
            "RentBee Payment Verified",
            f"Payment verified for {booking.item.name}! Ready for pickup.",
            {'url': f'/host-hub?tab=upcoming&highlight={booking.id}', 'booking_id': booking.id}
        )
    except Exception as e:
        logger.warning(f"Web push dispatch to owner failed: {e}")

    # 2. Notify renter
    renter = booking.renter
    renter_title = "Payment Successful!"
    renter_message = (
        f"Your payment of ₹{booking.total_amount} for booking #{booking.booking_reference} "
        f"({booking.item.name}) is confirmed. Coordinate pickup with the host."
    )
    InAppNotification.objects.get_or_create(
        user=renter,
        booking=booking,
        event='payment_verified_renter',
        defaults={'item': booking.item, 'title': renter_title, 'message': renter_message}
    )
    try:
        from .push_service import send_web_push
        send_web_push(
            renter,
            "RentBee Payment Successful",
            f"Payment confirmed for {booking.item.name}.",
            {'url': f'/bookings/{booking.id}', 'booking_id': booking.id}
        )
    except Exception as e:
        logger.warning(f"Web push dispatch to renter failed: {e}")


def confirm_offline_booking_payment(booking, user):
    """
    Confirms receipt of offline cash payment at pickup.
    Strictly authorized to the canonical item owner (host) or a staff admin.
    Renters and unrelated users are strictly rejected with PermissionDenied.
    Reuses existing payment_verified_at and payment_verified_by fields.
    Does not generate synthetic transaction IDs.
    """
    with transaction.atomic():
        locked_booking = (
            Booking.objects.select_for_update()
            .select_related('item', 'owner')
            .get(pk=booking.pk)
        )

        # 1. Authorization: Host or Staff Admin only
        is_owner = bool(locked_booking.owner_id is not None and locked_booking.owner_id == user.id)
        is_admin = bool(user.is_staff or user.is_superuser)

        if not (is_owner or is_admin):
            raise PermissionDenied("Only the item owner or an administrator can confirm offline payment.")

        # 2. Strict Renter Block
        if user.id == locked_booking.renter_id and not is_admin:
            raise PermissionDenied("Renters cannot confirm offline payment for their own bookings.")

        # 3. Method & Lifecycle Status Validation
        if getattr(locked_booking, 'payment_method', 'online') != 'offline':
            raise ValidationError({'error': 'Only offline Pay at Pickup bookings can be confirmed through this endpoint.'})

        if locked_booking.status != 'waiting_for_pickup':
            raise ValidationError({
                'error': f'Offline payment can only be confirmed for approved bookings waiting for pickup (current status: {locked_booking.get_status_display()}).'
            })

        # 4. Duplicate Confirmation Prevention
        if locked_booking.payment_status == 'paid':
            raise ValidationError({'error': 'Payment for this booking has already been verified.'})

        # 5. Mutate State (Reusing existing audit fields, no synthetic transaction ID)
        now = timezone.now()
        locked_booking.payment_status = 'paid'
        locked_booking.payment_verified_at = now
        locked_booking.payment_verified_by = user
        locked_booking.save(update_fields=[
            'payment_status',
            'payment_verified_at',
            'payment_verified_by',
            'updated_at'
        ])

        transaction.on_commit(lambda: notify_payment_verified(locked_booking))

    return locked_booking


def get_item_availability(item, start_date=None, end_date=None):
    """Peak reserved units over an inclusive date interval; stock is total inventory.

    Active rentals have no known release date until return is confirmed. Stale
    pending requests are excluded even when no expiry-maintenance view has run.
    """
    start_date = start_date or timezone.localdate()
    end_date = end_date or start_date
    reservations = Booking.objects.filter(item_id=item.pk, status__in=[
        'waiting_for_pickup', 'rental_in_progress',
    ]).filter(Q(status='rental_in_progress') | Q(start_date__lte=end_date)).filter(
        Q(status='rental_in_progress') | Q(end_date__gte=start_date)
    )
    events = {}
    for booking in reservations.only('start_date', 'end_date', 'status', 'requested_quantity'):
        left = start_date if booking.status == 'rental_in_progress' else max(start_date, booking.start_date)
        right = end_date if booking.status == 'rental_in_progress' else min(end_date, booking.end_date)
        quantity = max(1, booking.requested_quantity)
        events[left] = events.get(left, 0) + quantity
        # Endpoints are inclusive: a unit is released on the following day.
        if right < end_date:
            release = right + timedelta(days=1)
            events[release] = events.get(release, 0) - quantity
    peak = current = 0
    for day in sorted(events):
        current += events[day]
        peak = max(peak, current)
    total = max(0, item.stock)
    available = max(0, total - peak)
    rentable = (
        not item.is_deleted and item.is_published
        and item.category.is_active and not item.category.is_deleted
        and (not item.owner_id or item.owner.is_active)
    )
    if not rentable:
        available = 0
    return {
        'total_stock': total,
        'available_stock': available,
        'is_available': available > 0,
        'availability_reason': (
            'out_of_stock' if total == 0 else
            'unavailable' if not rentable else
            'reserved' if available == 0 else 'available'
        ),
    }


def notify_booking_event(booking, event):
    if event == 'requested':
        user = booking.item.owner
        title = 'New booking request!'
        message = f'A renter has requested {booking.requested_quantity} unit(s) of your item: {booking.item.name}.'
        renter_name = booking.renter.full_name or booking.renter.email
        push_title = 'RentBee'
        push_body = f'{renter_name} requested your {booking.item.name}.'
        push_data = {
            'url': f'/host-hub?tab=incoming&highlight={booking.id}',
            'booking_id': booking.id,
            'event': event,
        }
    elif event == 'accepted':
        user = booking.renter
        title = 'Your booking request has been accepted!'
        message = f'{booking.item.name}: {booking.get_status_display()}.'
        push_title = 'RentBee'
        push_body = f'Your request for {booking.item.name} has been approved.'
        push_data = {
            'url': f'/bookings/{booking.id}',
            'booking_id': booking.id,
            'event': event,
        }
    else:
        user = booking.renter
        title = 'Booking Request Rejected'
        rejected_time = booking.rejected_at or timezone.now()
        rejected_time_str = rejected_time.strftime('%d %b %Y, %I:%M %p')
        rejection_reason_text = booking.rejection_reason or 'No reason provided.'
        message = (
            f'Your booking request for {booking.item.name} (Booking #{booking.booking_reference}) has been rejected.\n'
            f'Reason: {rejection_reason_text}\n'
            f'Rejected on: {rejected_time_str}'
        )
        push_title = 'RentBee'
        push_body = f'Your request for {booking.item.name} was rejected. Reason: {rejection_reason_text}'
        push_data = {
            'url': f'/bookings/{booking.id}',
            'booking_id': booking.id,
            'event': event,
        }

    notification, _ = InAppNotification.objects.get_or_create(
        user=user, booking=booking, event=event,
        defaults={'item': booking.item, 'title': title, 'message': message})
    if event != 'requested':
        InAppNotification.objects.filter(
            booking=booking, event='requested', user=booking.owner).update(is_read=True)

    # Web Push Notification (Informational only, graceful error handling)
    try:
        from .push_service import send_web_push
        send_web_push(user, push_title, push_body, push_data)
    except Exception as e:
        logger.warning(f"Web push dispatch failed in notify_booking_event: {e}")

    return notification


def initiate_booking_refund(booking_or_id):
    """
    Reusable, idempotent service to request a 100% refund from Razorpay.
    Safety guarantees:
    - Verifies booking exists, has online payment method, and was captured/paid.
    - Preserves original payment_transaction_id.
    - Idempotent: checks existing refund status if already initiated.
    - If network error occurs, attempts reconciliation before failing.
    - Sets refund_status = 'pending' upon API acceptance; only sets
      payment_status = 'refunded' if Razorpay confirms processed status.
    - Calculates 100% of the captured amount (including rental amount and deposit).
    """
    booking_id = booking_or_id.id if hasattr(booking_or_id, 'id') else booking_or_id
    booking = Booking.objects.filter(id=booking_id).first()
    if not booking:
        raise ValidationError({'error': f'Booking with id {booking_id} does not exist.'})

    if getattr(booking, 'payment_method', 'online') == 'offline':
        raise ValidationError({'error': 'Razorpay refund cannot be initiated for offline Pay at Pickup bookings.'})

    if booking.payment_status not in ['paid', 'refunded']:
        raise ValidationError({'error': 'Refund can only be initiated for paid bookings.'})

    if not booking.payment_transaction_id:
        raise ValidationError({'error': 'Cannot initiate refund without payment_transaction_id.'})

    expected_amount_paise = int(round(booking.total_amount * 100))
    if expected_amount_paise <= 0:
        raise ValidationError({'error': 'Invalid refund amount.'})

    client = get_razorpay_client()

    # 1. Check if refund was already confirmed processed
    if booking.refund_status == 'processed' and booking.refund_transaction_id:
        return {
            'status': 'processed',
            'refund_id': booking.refund_transaction_id,
            'amount': booking.refund_amount or booking.total_amount,
        }

    # 2. Check if refund transaction already exists on booking: reconcile from Razorpay
    if booking.refund_transaction_id:
        try:
            rfnd_info = client.refund.fetch(booking.refund_transaction_id)
            remote_status = rfnd_info.get('status', 'pending')
            if remote_status == 'processed':
                booking.refund_status = 'processed'
                booking.payment_status = 'refunded'
                if not booking.refunded_at:
                    booking.refunded_at = timezone.now()
                booking.save(update_fields=['refund_status', 'payment_status', 'refunded_at', 'updated_at'])
            return {
                'status': booking.refund_status,
                'refund_id': booking.refund_transaction_id,
                'amount': booking.refund_amount or booking.total_amount,
                'reconciled': True,
            }
        except Exception as e:
            logger.warning(f"Failed to fetch refund {booking.refund_transaction_id} from Razorpay: {e}")

    # 3. Check if Razorpay already has a refund for this payment (reconciliation before creating duplicate)
    try:
        existing_refunds = client.payment.fetch_multiple_refund(booking.payment_transaction_id)
        items = existing_refunds.get('items', []) if isinstance(existing_refunds, dict) else []
        for r in items:
            if r.get('amount') == expected_amount_paise:
                rfnd_id = r.get('id')
                rfnd_status = r.get('status', 'pending')
                booking.refund_transaction_id = rfnd_id
                booking.refund_amount = booking.total_amount
                booking.refund_status = 'processed' if rfnd_status == 'processed' else 'pending'
                if rfnd_status == 'processed':
                    booking.payment_status = 'refunded'
                    if not booking.refunded_at:
                        booking.refunded_at = timezone.now()
                booking.save(update_fields=[
                    'refund_transaction_id', 'refund_amount', 'refund_status',
                    'payment_status', 'refunded_at', 'updated_at'
                ])
                return {
                    'status': booking.refund_status,
                    'refund_id': rfnd_id,
                    'amount': booking.total_amount,
                    'reconciled': True,
                }
    except Exception as e:
        logger.warning(f"Error checking existing refunds on payment {booking.payment_transaction_id}: {e}")

    # 4. Request new refund from Razorpay
    receipt = f"rf_{booking.id}_{uuid.uuid4().hex[:8]}"[:40]
    refund_data = {
        'amount': expected_amount_paise,
        'notes': {
            'booking_id': str(booking.id),
            'booking_reference': booking.booking_reference,
            'renter_id': str(booking.renter_id),
            'refund_type': '100_percent_cancellation',
            'cancellation_fee': '0.00',
        },
        'receipt': receipt,
    }

    try:
        refund_res = client.payment.refund(booking.payment_transaction_id, refund_data)
    except Exception as exc:
        logger.error(f"Failed to request Razorpay refund for booking {booking.booking_reference}: {exc}")
        # Network timeout / error recovery: attempt to reconcile in case request reached Razorpay
        try:
            recon = client.payment.fetch_multiple_refund(booking.payment_transaction_id)
            items = recon.get('items', []) if isinstance(recon, dict) else []
            for r in items:
                if r.get('amount') == expected_amount_paise:
                    rfnd_id = r.get('id')
                    rfnd_status = r.get('status', 'pending')
                    booking.refund_transaction_id = rfnd_id
                    booking.refund_amount = booking.total_amount
                    booking.refund_status = 'processed' if rfnd_status == 'processed' else 'pending'
                    if rfnd_status == 'processed':
                        booking.payment_status = 'refunded'
                        if not booking.refunded_at:
                            booking.refunded_at = timezone.now()
                    booking.save(update_fields=[
                        'refund_transaction_id', 'refund_amount', 'refund_status',
                        'payment_status', 'refunded_at', 'updated_at'
                    ])
                    return {
                        'status': booking.refund_status,
                        'refund_id': rfnd_id,
                        'amount': booking.total_amount,
                        'reconciled': True,
                    }
        except Exception:
            pass

        booking.refund_status = 'failed'
        booking.refund_error = str(exc)
        booking.save(update_fields=['refund_status', 'refund_error', 'updated_at'])
        return {
            'status': 'failed',
            'error': str(exc),
        }

    rfnd_id = refund_res.get('id')
    rfnd_status = refund_res.get('status', 'pending')
    booking.refund_transaction_id = rfnd_id
    booking.refund_amount = booking.total_amount
    booking.refund_error = ''

    if rfnd_status == 'processed':
        booking.refund_status = 'processed'
        booking.payment_status = 'refunded'
        booking.refunded_at = timezone.now()
    else:
        booking.refund_status = 'pending'
        # payment_status stays 'paid' until confirmed!

    booking.save(update_fields=[
        'refund_transaction_id', 'refund_amount', 'refund_status',
        'refund_error', 'payment_status', 'refunded_at', 'updated_at'
    ])

    return {
        'status': booking.refund_status,
        'refund_id': rfnd_id,
        'amount': booking.total_amount,
    }


def confirm_offline_refund(booking, user):
    """
    Confirms manual cash return for a cancelled offline booking.
    Strictly authorized to canonical item owner or staff admin.
    Renters and third parties are rejected with PermissionDenied.
    """
    with transaction.atomic():
        locked_booking = Booking.objects.select_for_update().select_related('item', 'owner').get(pk=booking.pk)
        is_owner = bool(locked_booking.owner_id is not None and locked_booking.owner_id == user.id)
        is_admin = bool(user.is_staff or user.is_superuser)

        if not (is_owner or is_admin):
            raise PermissionDenied("Only the item owner or an administrator can confirm cash refund.")

        if user.id == locked_booking.renter_id and not is_admin:
            raise PermissionDenied("Renters cannot confirm cash refund for their own bookings.")

        if getattr(locked_booking, 'payment_method', 'online') != 'offline':
            raise ValidationError({'error': 'Only offline Pay at Pickup bookings can use offline cash refund confirmation.'})

        if locked_booking.status != 'cancelled':
            raise ValidationError({'error': 'Cash refund can only be confirmed for cancelled bookings.'})

        if locked_booking.payment_status != 'paid':
            raise ValidationError({'error': 'Cannot refund cash for a booking where cash payment was never collected.'})

        now = timezone.now()
        locked_booking.cash_returned_at = now
        locked_booking.cash_returned_by = user
        locked_booking.payment_status = 'refunded'
        locked_booking.refund_status = 'processed'
        locked_booking.refunded_at = now
        locked_booking.refund_amount = locked_booking.total_amount
        locked_booking.save(update_fields=[
            'cash_returned_at', 'cash_returned_by', 'payment_status',
            'refund_status', 'refunded_at', 'refund_amount', 'updated_at'
        ])
    return locked_booking


def notify_refund_processed(booking):
    """
    Sends notification to renter and host when refund is confirmed processed.
    """
    renter = booking.renter
    title = "Refund Processed!"
    message = (
        f"Your 100% refund of ₹{booking.refund_amount or booking.total_amount} for booking #{booking.booking_reference} "
        f"({booking.item.name}) has been successfully processed."
    )
    InAppNotification.objects.get_or_create(
        user=renter,
        booking=booking,
        event='refund_processed_renter',
        defaults={'item': booking.item, 'title': title, 'message': message}
    )
    try:
        from .push_service import send_web_push
        send_web_push(
            renter,
            "RentBee Refund Processed",
            f"₹{booking.refund_amount or booking.total_amount} refunded for {booking.item.name}.",
            {'url': f'/bookings/{booking.id}', 'booking_id': booking.id}
        )
    except Exception as e:
        logger.warning(f"Web push dispatch failed in notify_refund_processed: {e}")

