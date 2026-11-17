from django.urls import path
from .views import (
    AdminUserListView,
    AdminUserDetailView,
    AdminUserBlockView,
    AdminBookingListView,
    AdminBookingDetailView,
    AdminBookingStatusTransitionView,
    AdminReturnActionView,
    AdminInventoryListView,
    AdminStockUpdateView,
)

urlpatterns = [
    # User Management
    path("users/", AdminUserListView.as_view(), name="admin-user-list"),
    path("users/<int:pk>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("users/<int:pk>/status/", AdminUserBlockView.as_view(), name="admin-user-block"),

    # Booking Management
    path("bookings/", AdminBookingListView.as_view(), name="admin-booking-list"),
    path("bookings/<int:pk>/", AdminBookingDetailView.as_view(), name="admin-booking-detail"),
    path("bookings/<int:pk>/status/", AdminBookingStatusTransitionView.as_view(), name="admin-booking-status"),
    path("bookings/<int:pk>/return-action/", AdminReturnActionView.as_view(), name="admin-return-action"),

    # Inventory / Stock Management
    path("inventory/", AdminInventoryListView.as_view(), name="admin-inventory-list"),
    path("inventory/<int:pk>/stock/", AdminStockUpdateView.as_view(), name="admin-inventory-stock-update"),
]
