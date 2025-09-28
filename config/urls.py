from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("", include(("inventory.urls", "inventory"), namespace="inventory")),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("admin/", admin.site.urls),
    path("manager/", include("accounts.manager_urls")),
    path("api/", include("api.urls")),
    path("cart/", include(("cart.urls", "cart"), namespace="cart")),
    path("mockpay/", include("mockpay.urls", namespace="mockpay")),

    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
