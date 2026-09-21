import json
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views import View
from .services.chatbot_service import ChatbotService


class ChatbotInterfaceView(TemplateView):
    template_name = 'chatbot/chat.html'


class ChatbotMessageApiView(View):
    """
    Asynchronous JSON API for the conversational agent.
    Routes user prompts to ChatbotService and returns synthesized responses,
    sources, and two-step action confirmation state.
    """
    def post(self, request, *args, **kwargs):
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST

            text = data.get('message', '').strip()
            session_key = data.get('session_key') or request.session.session_key
            if not session_key:
                request.session.save()
                session_key = request.session.session_key

            if not text:
                return JsonResponse({'error': 'Message text is required.'}, status=400)

            user = request.user if request.user.is_authenticated else None
            response_data = ChatbotService.process_user_message(
                session_key=session_key,
                user_input=text,
                user=user,
            )

            return JsonResponse(response_data)
        except Exception as e:
            return JsonResponse({
                'error': f"Internal chatbot processing error: {str(e)}",
                'message': "I encountered an error processing your request. Please try again.",
                'sources': [],
            }, status=500)
