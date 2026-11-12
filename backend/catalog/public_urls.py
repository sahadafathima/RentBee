from django.urls import path
from .views import OwnerItemListView, OwnerItemDetailView, OwnerItemDeactivateView, PublicItemListView, PublicItemDetailView

urlpatterns = [
    path('mine/', OwnerItemListView.as_view(), name='owner-items'),
    path('mine/<int:pk>/', OwnerItemDetailView.as_view(), name='owner-item-detail'),
    path('mine/<int:pk>/deactivate/', OwnerItemDeactivateView.as_view(), name='owner-item-deactivate'),
    path('', PublicItemListView.as_view(), name='public-item-list'),
    path('<int:pk>/', PublicItemDetailView.as_view(), name='public-item-detail'),
]

