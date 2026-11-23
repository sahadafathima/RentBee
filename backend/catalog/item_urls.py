from django.urls import path
from .views import AdminItemListCreateView, AdminItemDetailView, AdminItemSoftDeleteView

urlpatterns = [
    path('', AdminItemListCreateView.as_view(), name='admin-item-list-create'),
    path('<int:pk>/', AdminItemDetailView.as_view(), name='admin-item-detail'),
    path('<int:pk>/delete/', AdminItemSoftDeleteView.as_view(), name='admin-item-soft-delete'),
]

