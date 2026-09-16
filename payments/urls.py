from django.urls import path
from .views import CheckoutView, PaymentSuccessView

app_name = 'payments'

urlpatterns = [
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('success/', PaymentSuccessView.as_view(), name='success'),
]
