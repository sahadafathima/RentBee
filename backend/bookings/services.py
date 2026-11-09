from datetime import timedelta
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from .models import Booking, AvailabilityNotificationRequest, InAppNotification


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
        conflicts = check_item_conflicts(item_id, req.start_date, req.end_date)
        if not conflicts.exists():
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
    
    expired_qs = Booking.objects.filter(
        status='pending_approval',
        created_at__lt=cutoff
    )
    count = expired_qs.count()
    if count > 0:
        affected_item_ids = list(expired_qs.values_list('item_id', flat=True).distinct())
        expired_qs.update(status='expired', updated_at=timezone.now())
        for item_id in affected_item_ids:
            process_availability_notifications_for_item(item_id)
    return count


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


def check_item_conflicts(item_id, start_date, end_date, exclude_booking_id=None):
    """
    Returns queryset of active conflicting bookings for the specified item and date range.
    Two bookings conflict if: (start_date <= other.end_date) and (end_date >= other.start_date).
    Automatically runs opportunistic pending-expiry first.
    """
    expire_stale_pending_bookings()

    active_statuses = ['waiting_for_pickup', 'rental_in_progress', 'pending_approval']
    
    qs = Booking.objects.filter(
        item_id=item_id,
        status__in=active_statuses,
        start_date__lte=end_date,
        end_date__gte=start_date
    )

    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)

    return qs

