from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("users.urls")),
    path(
        "api/token/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path("accounts/", include("allauth.urls")),
    path('api/addresses/', include('addresses.urls')),
    path('api/admin/categories/', include('catalog.urls')),
    path('api/admin/items/', include('catalog.item_urls')),
    path('api/items/', include('catalog.public_urls')),
    path('api/admin/', include('admin_panel.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
