import uuid
from datetime import timedelta
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


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
        ('refunded', 'Refunded'),
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
    rental_amount = models.DecimalField(max_digits=10, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='pending_approval'
    )

    # Payment Security & Audit
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
    def return_deadline(self):
        """
        Exact return deadline calculated by adding selected rental duration
        in 24-hour periods to the actual owner pickup confirmation timestamp (picked_up_at).
        Returns None if the booking has not been picked up yet.
        """
        if self.picked_up_at and self.duration_days:
            return self.picked_up_at + timedelta(days=self.duration_days)
        return None

    @property
    def return_deadline_display(self):
        """
        Asia/Kolkata formatted string of return_deadline for display.
        """
        deadline = self.return_deadline
        if not deadline:
            return None
        import zoneinfo
        kolkata_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
        kolkata_dt = deadline.astimezone(kolkata_tz)
        return kolkata_dt.strftime('%d %b %Y, %I:%M %p IST')

    @property
    def picked_up_at_display(self):
        """
        Asia/Kolkata formatted string of picked_up_at for display.
        """
        if not self.picked_up_at:
            return None
        import zoneinfo
        kolkata_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
        kolkata_dt = self.picked_up_at.astimezone(kolkata_tz)
        return kolkata_dt.strftime('%d %b %Y, %I:%M %p IST')

    @property
    def returned_at_display(self):
        """
        Asia/Kolkata formatted string of returned_at for display.
        """
        if not self.returned_at:
            return None
        import zoneinfo
        kolkata_tz = zoneinfo.ZoneInfo('Asia/Kolkata')
        kolkata_dt = self.returned_at.astimezone(kolkata_tz)
        return kolkata_dt.strftime('%d %b %Y, %I:%M %p IST')


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



