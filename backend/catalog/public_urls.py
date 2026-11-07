from django.urls import path
from .views import PublicItemListView, PublicItemDetailView

urlpatterns = [
    path('', PublicItemListView.as_view(), name='public-item-list'),
    path('<int:pk>/', PublicItemDetailView.as_view(), name='public-item-detail'),
]

