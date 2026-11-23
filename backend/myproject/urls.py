from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from catalog.views import PublicCategoryListView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("users.urls")),
    path("accounts/", include("allauth.urls")),
    path('api/addresses/', include('addresses.urls')),
    path('api/categories/', PublicCategoryListView.as_view(), name='public-category-list'),
    path('api/admin/categories/', include('catalog.urls')),
    path('api/admin/items/', include('catalog.item_urls')),
    path('api/items/', include('catalog.public_urls')),
    path('api/wishlist/', include('catalog.wishlist_urls')),
    path('api/bookings/', include('bookings.urls')),
    path('api/admin/', include('admin_panel.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
