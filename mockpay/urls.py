from django.urls import path
from .views import checkout_page, checkout_success, result

app_name = "mockpay"

urlpatterns = [
    path("checkout/<str:client_secret>/", checkout_page, name="checkout_page"),
    path("result/<str:client_secret>/", result, name="result"),
    path("pay/<str:client_secret>/", checkout_page, name="checkout_page"),
    path(
        "pay/<str:client_secret>/success/",
        checkout_success,
        name="checkout_success",
    ),
]
