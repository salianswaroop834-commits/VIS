from datetime import datetime
from django.conf import settings


def platform_context(request):
    """
    Exposes platform brand identity, educational disclaimers,
    runtime environment flags, and notification counts to all templates.
    """
    ctx = {
        'PLATFORM_NAME': getattr(settings, 'PLATFORM_NAME', 'Nexisure Vehicle Insurance'),
        'PROTOTYPE_DISCLAIMER': getattr(
            settings,
            'PROTOTYPE_DISCLAIMER',
            'Educational prototype platform: Synthetic data and simulated transactions only.'
        ),
        'CURRENT_YEAR': datetime.now().year,
        'IS_DEBUG': settings.DEBUG,
        'unread_notification_count': 0,
    }

    # Inject unread notification count for authenticated users
    if request.user.is_authenticated:
        try:
            from core.models import Notification
            ctx['unread_notification_count'] = Notification.objects.filter(
                recipient=request.user,
                is_read=False,
            ).count()
        except Exception:
            ctx['unread_notification_count'] = 0

    return ctx
