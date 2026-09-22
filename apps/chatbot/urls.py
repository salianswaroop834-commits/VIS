from django.urls import path
from .views import ChatbotInterfaceView, ChatbotMessageApiView

app_name = 'chatbot'

urlpatterns = [
    path('', ChatbotInterfaceView.as_view(), name='chat'),
    path('api/message/', ChatbotMessageApiView.as_view(), name='api-message'),
]
