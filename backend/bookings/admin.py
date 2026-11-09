from django.contrib import admin
from .models import Booking, IssueReport
from .services import mark_booking_payment_verified


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


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        'booking_reference', 'item', 'renter', 'owner',
        'status', 'payment_status', 'start_date', 'end_date', 'duration_days', 'total_amount', 'created_at'
    ]
    list_filter = ['status', 'payment_status', 'created_at']
    search_fields = [
        'booking_reference', 'item__name', 'renter__email',
        'renter__full_name', 'owner__email', 'owner__full_name'
    ]
    readonly_fields = [
        'booking_reference', 'created_at', 'updated_at',
        'approved_at', 'rejected_at', 'picked_up_at', 'return_deadline_display', 'returned_at',
        'cancelled_at', 'payment_verified_at', 'payment_verified_by'
    ]
    actions = [verify_payment_action]


@admin.register(IssueReport)
class IssueReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'booking', 'renter', 'owner', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = [
        'booking__booking_reference', 'renter__email',
        'owner__email', 'description'
    ]
    readonly_fields = ['created_at', 'updated_at']

