import json
import uuid
import zoneinfo
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

KOLKATA_TZ = zoneinfo.ZoneInfo('Asia/Kolkata')


def _format_kolkata_dt(dt):
    """Formats a datetime in Asia/Kolkata timezone with IST suffix."""
    if not dt:
        return None
    return dt.astimezone(KOLKATA_TZ).strftime('%d %b %Y, %I:%M %p IST')


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending_approval', 'Waiting for Owner Approval'),
        ('waiting_for_pickup', 'Waiting for Pickup'),
        ('rental_in_progress', 'Rental in Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled by Renter'),
        ('rejected', 'Declined by Owner'),
        ('expired', 'Request Expired'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Payment Verified'),
        ('failed', 'Payment Failed'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('online', 'Online Payment (Razorpay)'),
        ('offline', 'Pay at Pickup (Cash)'),
    ]

    REFUND_STATUS_CHOICES = [
        ('pending', 'Refund Processing'),
        ('processed', 'Refund Completed'),
        ('failed', 'Refund Failed'),
    ]

    booking_reference = models.CharField(max_length=25, unique=True, editable=False)
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    item = models.ForeignKey(
        'catalog.Item',
        on_delete=models.PROTECT,
        related_name='bookings'
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_bookings'
    )

    start_date = models.DateField()
    end_date = models.DateField()
    duration_days = models.PositiveIntegerField()
    # Immutable number of physical units requested at booking time.
    requested_quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    # Immutable booking-time pricing snapshots
    daily_price = models.DecimalField(max_digits=10, decimal_places=2)
    original_rental_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    discount_type = models.CharField(max_length=50, blank=True, default='')
    rental_amount = models.DecimalField(max_digits=10, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='pending_approval'
    )

    # Delivery & Contact Address
    renter_address = models.ForeignKey(
        'addresses.Address',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bookings'
    )
    renter_address_snapshot = models.TextField(blank=True, default='')

    # Payment Security & Audit
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='online'
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )
    payment_verified_at = models.DateTimeField(null=True, blank=True)
    payment_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_payments'
    )
    payment_transaction_id = models.CharField(max_length=100, blank=True, default='')
    razorpay_order_id = models.CharField(max_length=100, blank=True, default='', db_index=True)

    # Refund Security & Audit
    refund_transaction_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refund_status = models.CharField(
        max_length=20,
        choices=REFUND_STATUS_CHOICES,
        blank=True,
        default=''
    )
    refund_initiated_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_error = models.TextField(blank=True, default='')

    # Manual Offline Cash Return Tracking
    cash_returned_at = models.DateTimeField(null=True, blank=True)
    cash_returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_cash_returns'
    )

    # Lifecycle Audit Timestamps & Actors
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_bookings'
    )
    cancellation_reason = models.TextField(blank=True, default='')

    picked_up_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)

    # Pickup OTP Verification & Handover Audit
    pickup_otp_hash = models.CharField(max_length=128, blank=True, default='')
    pickup_otp_expires_at = models.DateTimeField(null=True, blank=True)
    pickup_otp_attempts = models.PositiveSmallIntegerField(default=0)
    pickup_otp_created_at = models.DateTimeField(null=True, blank=True)
    pickup_otp_verified_at = models.DateTimeField(null=True, blank=True)
    pickup_confirmed_at = models.DateTimeField(null=True, blank=True)
    pickup_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_pickups'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            # Generate human-friendly reference: BK-XXXXXX
            random_suffix = uuid.uuid4().hex[:6].upper()
            self.booking_reference = f"BK-{random_suffix}"
            while Booking.objects.filter(booking_reference=self.booking_reference).exclude(pk=self.pk).exists():
                random_suffix = uuid.uuid4().hex[:6].upper()
                self.booking_reference = f"BK-{random_suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.booking_reference} - {self.item.name} ({self.get_status_display()})"

    def is_payment_verified(self):
        return self.payment_status == 'paid'

    def is_expired_pending(self):
        if self.status != 'pending_approval':
            return False
        expiry_hours = getattr(settings, 'RENTAL_PENDING_APPROVAL_EXPIRY_HOURS', 24)
        return timezone.now() > (self.created_at + timedelta(hours=expiry_hours))

    def can_renter_cancel(self):
        return self.status in ['pending_approval', 'waiting_for_pickup']

    @property
    def renter_address_data(self):
        """
        Returns structured address dictionary from snapshot or active foreign key.
        Preserves historical address details even if the address is edited or deleted later.
        """
        if self.renter_address_snapshot:
            try:
                parsed = json.loads(self.renter_address_snapshot)
                if isinstance(parsed, dict) and parsed:
                    return parsed
            except Exception:
                pass
        if self.renter_address:
            addr = self.renter_address
            return {
                'id': addr.id,
                'full_name': addr.full_name,
                'house_number': addr.house_number,
                'address': addr.address,
                'area': addr.area,
                'landmark': addr.landmark or '',
                'city': addr.city,
                'state': addr.state,
                'pincode': addr.pincode,
                'country': addr.country,
                'address_type': addr.address_type,
                'full_formatted_address': (
                    f"{addr.house_number}, {addr.address}, {addr.area}, "
                    f"{addr.landmark + ', ' if addr.landmark else ''}"
                    f"{addr.city}, {addr.state} - {addr.pincode}"
                )
            }
        # Fallback to renter's first address if legacy booking
        first_addr = self.renter.addresses.first() if self.renter else None
        if first_addr:
            return {
                'id': first_addr.id,
                'full_name': first_addr.full_name,
                'house_number': first_addr.house_number,
                'address': first_addr.address,
                'area': first_addr.area,
                'landmark': first_addr.landmark or '',
                'city': first_addr.city,
                'state': first_addr.state,
                'pincode': first_addr.pincode,
                'country': first_addr.country,
                'address_type': first_addr.address_type,
                'full_formatted_address': (
                    f"{first_addr.house_number}, {first_addr.address}, {first_addr.area}, "
                    f"{first_addr.landmark + ', ' if first_addr.landmark else ''}"
                    f"{first_addr.city}, {first_addr.state} - {first_addr.pincode}"
                )
            }
        return None

    @property
    def return_deadline(self):
        """
        Exact return deadline calculated by adding selected rental duration
        in 24-hour periods to the actual owner pickup confirmation timestamp.
        Returns None if the booking has not been picked up yet.
        """
        effective_pickup_time = self.pickup_confirmed_at or self.picked_up_at
        if effective_pickup_time and self.duration_days:
            return effective_pickup_time + timedelta(days=self.duration_days)
        return None

    @property
    def return_deadline_display(self):
        """
        Asia/Kolkata formatted string of return_deadline for display.
        """
        return _format_kolkata_dt(self.return_deadline)

    @property
    def pickup_confirmed_at_display(self):
        """
        Asia/Kolkata formatted string of pickup_confirmed_at for display.
        """
        return _format_kolkata_dt(self.pickup_confirmed_at or self.picked_up_at)

    @property
    def picked_up_at_display(self):
        """
        Asia/Kolkata formatted string of picked_up_at for display.
        """
        return _format_kolkata_dt(self.pickup_confirmed_at or self.picked_up_at)

    @property
    def renter_phone_masked(self):
        """
        Returns masked phone number of renter (e.g. ******3210).
        """
        phone = getattr(self.renter, 'phone_number', '') or ''
        if not phone:
            return ''
        digits = ''.join(ch for ch in phone if ch.isdigit())
        if len(digits) <= 4:
            return phone
        return f"{'*' * (len(digits) - 4)}{digits[-4:]}"

    @property
    def returned_at_display(self):
        """
        Asia/Kolkata formatted string of returned_at for display.
        """
        return _format_kolkata_dt(self.returned_at)

    @property
    def refunded_at_display(self):
        """
        Asia/Kolkata formatted string of refunded_at for display.
        """
        return _format_kolkata_dt(self.refunded_at)

    @property
    def cash_returned_at_display(self):
        """
        Asia/Kolkata formatted string of cash_returned_at for display.
        """
        return _format_kolkata_dt(self.cash_returned_at)


class IssueReport(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved', 'Resolved'),
    ]

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='issue_reports'
    )
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='filed_issue_reports'
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_issue_reports'
    )

    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Issue for {self.booking.booking_reference} by {self.renter.email}"


class AvailabilityNotificationRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='availability_requests'
    )
    item = models.ForeignKey(
        'catalog.Item',
        on_delete=models.CASCADE,
        related_name='availability_requests'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_notified = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'item', 'start_date', 'end_date')

    def __str__(self):
        return f"Notify {self.user.email} for {self.item.name} ({self.start_date} -> {self.end_date})"


class InAppNotification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='in_app_notifications'
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    item = models.ForeignKey(
        'catalog.Item',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications')
    event = models.CharField(max_length=30, blank=True, default='')

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'booking', 'event'],
                                    name='unique_booking_notification_event')
        ]

    def __str__(self):
        return f"Notification to {self.user.email}: {self.title}"


class PushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='push_subscriptions'
    )
    endpoint = models.TextField()
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'endpoint'],
                                    name='unique_user_push_endpoint')
        ]

    def __str__(self):
        return f"PushSubscription for {self.user.email} ({self.endpoint[:30]}...)"


class ProcessedWebhookEvent(models.Model):
    """
    Idempotency registry for inbound Razorpay webhook events.
    Guarantees that re-delivered webhook payloads are processed exactly once.
    """
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=50, blank=True, default='')
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-processed_at']

    def __str__(self):
        return f"{self.event_id} ({self.event_type})"



