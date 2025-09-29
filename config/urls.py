from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView, RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path("", include(("inventory.urls", "inventory"), namespace="inventory")),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("cart/", include(("cart.urls", "cart"), namespace="cart")),
    path("mockpay/", include("mockpay.urls", namespace="mockpay")),
    path("ws-test/", TemplateView.as_view(template_name="ws_test.html"), name="ws-test"),
]

urlpatterns += [
    re_path(r"^manager/(?P<rest>.*)$",
            RedirectView.as_view(url="/accounts/manager/%(rest)s", permanent=False),
            name="redirect-manager-under-accounts"),
]
