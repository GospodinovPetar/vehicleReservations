from django.urls import path
from . import views

app_name = "mockpay"

urlpatterns = [
    path("checkout/<str:client_secret>/", views.checkout_page, name="checkout_page"),

    path("challenge/<str:client_secret>/", views.challenge, name="challenge"),

    path("result/<str:client_secret>/", views.result, name="result"),
]