from django.urls import path
from .views import (
    MyBookingsListView,
    BookingCreateView,
    BookingDetailView,
    CancelBookingView,
    OwnerApproveBookingView,
    OwnerRejectBookingView,
    ConfirmPickupView,
    ConfirmReturnView,
    ReportProblemView,
    HostBookingsListView,
    HostReportsListView,
    CheckAvailabilityView,
    NotifyAvailabilityView,
    NotificationsListView,
    MarkNotificationReadView,
    MarkAllNotificationsReadView,
)

urlpatterns = [
    path('my-bookings/', MyBookingsListView.as_view(), name='my-bookings'),
    path('check-availability/', CheckAvailabilityView.as_view(), name='check-availability'),
    path('notify-availability/', NotifyAvailabilityView.as_view(), name='notify-availability'),
    path('notifications/', NotificationsListView.as_view(), name='notifications-list'),
    path('notifications/<int:pk>/mark-read/', MarkNotificationReadView.as_view(), name='notification-mark-read'),
    path('notifications/mark-all-read/', MarkAllNotificationsReadView.as_view(), name='notifications-mark-all-read'),
    path('', BookingCreateView.as_view(), name='booking-create'),
    path('<int:pk>/', BookingDetailView.as_view(), name='booking-detail'),
    path('<int:pk>/cancel/', CancelBookingView.as_view(), name='booking-cancel'),
    path('<int:pk>/approve/', OwnerApproveBookingView.as_view(), name='booking-approve'),
    path('<int:pk>/reject/', OwnerRejectBookingView.as_view(), name='booking-reject'),
    path('<int:pk>/confirm-pickup/', ConfirmPickupView.as_view(), name='booking-confirm-pickup'),
    path('<int:pk>/confirm-return/', ConfirmReturnView.as_view(), name='booking-confirm-return'),
    path('<int:pk>/report-problem/', ReportProblemView.as_view(), name='booking-report-problem'),
    path('host/requests/', HostBookingsListView.as_view(), name='host-requests'),
    path('host/reports/', HostReportsListView.as_view(), name='host-reports'),
]

