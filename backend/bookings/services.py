from datetime import timedelta
import logging
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from functools import wraps
from catalog.models import Item
from django.utils import timezone
from .models import Booking, AvailabilityNotificationRequest, InAppNotification

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
    Exclusively invoked by staff admin action, backend CLI, or future payment gateway webhook.
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


def get_item_availability(item, start_date=None, end_date=None):
    """Peak reserved units over an inclusive date interval; stock is total inventory.

    Active rentals have no known release date until return is confirmed. Stale
    pending requests are excluded even when no expiry-maintenance view has run.
    """
    start_date = start_date or timezone.localdate()
    end_date = end_date or start_date
    cutoff = timezone.now() - timedelta(
        hours=getattr(settings, 'RENTAL_PENDING_APPROVAL_EXPIRY_HOURS', 24))
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
    else:
        user = booking.renter
        title = ('Your booking request has been accepted!' if event == 'accepted'
                 else 'Your booking request was rejected.')
        message = f'{booking.item.name}: {booking.get_status_display()}.'
        if event == 'rejected' and booking.rejection_reason:
            message += f' Reason: {booking.rejection_reason}'
        push_title = 'RentBee'
        if event == 'accepted':
            push_body = f'Your request for {booking.item.name} has been approved.'
        else:
            push_body = f'Your request for {booking.item.name} was declined.'
            if booking.rejection_reason:
                push_body += f' Reason: {booking.rejection_reason}'
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
