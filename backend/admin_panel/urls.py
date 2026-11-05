from django.urls import path
from .views import AdminUserListView, AdminUserDetailView ,  AdminUserBlockView

urlpatterns = [
    path(
        "users/",
        AdminUserListView.as_view(),
        name="admin-user-list"
    ),

    path(
        "users/<int:pk>/",
        AdminUserDetailView.as_view(),
        name="admin-user-detail"
    ),

    path(
    "users/<int:pk>/status/",
    AdminUserBlockView.as_view(),
    name="admin-user-block",
),
]