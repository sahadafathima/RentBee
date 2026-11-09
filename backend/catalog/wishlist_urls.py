from django.urls import path
from .views import WishlistListView, WishlistToggleView, WishlistDetailView

urlpatterns = [
    path('', WishlistListView.as_view(), name='wishlist-list-create'),
    path('toggle/', WishlistToggleView.as_view(), name='wishlist-toggle'),
    path('<int:item_id>/', WishlistDetailView.as_view(), name='wishlist-detail'),
]

