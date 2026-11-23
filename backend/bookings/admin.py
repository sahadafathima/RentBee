from django.contrib import admin
from .models import Booking, IssueReport, ProcessedWebhookEvent
from .services import mark_booking_payment_verified, confirm_offline_booking_payment


@admin.action(description="Mark selected bookings as Payment Verified")
def verify_payment_action(modeladmin, request, queryset):
    count = 0
    for booking in queryset:
        if booking.payment_status != 'paid':
            mark_booking_payment_verified(
                booking,
                verified_by=request.user,
                transaction_id=f"ADMIN-VERIFY-{booking.id}"
            )
            count += 1
    modeladmin.message_user(request, f"{count} booking(s) marked as Payment Verified.")


@admin.action(description="Confirm Offline Payment for selected bookings")
def confirm_offline_payment_action(modeladmin, request, queryset):
    success_count = 0
    error_count = 0
    for booking in queryset:
        try:
            confirm_offline_booking_payment(booking, request.user)
            success_count += 1
        except Exception:
            error_count += 1
    if error_count:
        modeladmin.message_user(request, f"{success_count} offline booking(s) confirmed, {error_count} skipped/failed.")
    else:
        modeladmin.message_user(request, f"{success_count} offline booking(s) confirmed successfully.")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        'booking_reference', 'item', 'renter', 'owner',
        'status', 'payment_status', 'payment_method', 'start_date', 'end_date', 'duration_days',
        'original_rental_amount', 'discount_amount', 'total_amount', 'created_at'
    ]
    list_filter = ['status', 'payment_status', 'payment_method', 'discount_type', 'created_at']
    search_fields = [
        'booking_reference', 'razorpay_order_id', 'payment_transaction_id',
        'item__name', 'renter__email',
        'renter__full_name', 'owner__email', 'owner__full_name'
    ]
    readonly_fields = [
        'booking_reference', 'payment_method', 'created_at', 'updated_at',
        'original_rental_amount', 'discount_amount', 'discount_percentage', 'discount_type',
        'approved_at', 'rejected_at', 'picked_up_at', 'return_deadline_display', 'returned_at',
        'cancelled_at', 'payment_verified_at', 'payment_verified_by',
        'razorpay_order_id', 'payment_transaction_id'
    ]
    actions = [verify_payment_action, confirm_offline_payment_action]


@admin.register(ProcessedWebhookEvent)
class ProcessedWebhookEventAdmin(admin.ModelAdmin):
    list_display = ['event_id', 'event_type', 'processed_at']
    search_fields = ['event_id', 'event_type']
    readonly_fields = ['event_id', 'event_type', 'processed_at']


@admin.register(IssueReport)
class IssueReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'booking', 'renter', 'owner', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = [
        'booking__booking_reference', 'renter__email',
        'owner__email', 'description'
    ]
    readonly_fields = ['created_at', 'updated_at']

