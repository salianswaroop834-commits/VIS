from django.urls import path
from .views import (
    LoginView,
    RegisterView,
    OtpRequestView,
    OtpVerifyView,
    ProfileView,
    LogoutView,
)

app_name = 'accounts'

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('otp/request/', OtpRequestView.as_view(), name='otp-request'),
    path('verify-otp/', OtpVerifyView.as_view(), name='verify-otp'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
