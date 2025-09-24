from django.urls import path
from . import views

app_name = "mockpay"

urlpatterns = [
    path("checkout/<str:client_secret>/", views.checkout_page, name="checkout_page"),
    path("result/<str:client_secret>/", views.result, name="result"),
    path("pay/<str:client_secret>/", views.checkout_page, name="checkout_page"),
    path("pay/<str:client_secret>/success/", views.checkout_success, name="checkout_success"),
]