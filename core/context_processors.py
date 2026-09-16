from datetime import datetime
from django.conf import settings


def platform_context(request):
    """
    Exposes platform brand identity, educational disclaimers,
    and runtime environment flags to all templates.
    """
    return {
        'PLATFORM_NAME': getattr(settings, 'PLATFORM_NAME', 'Nexisure Vehicle Insurance'),
        'PROTOTYPE_DISCLAIMER': getattr(
            settings,
            'PROTOTYPE_DISCLAIMER',
            'Educational prototype platform: Synthetic data and simulated transactions only.'
        ),
        'CURRENT_YEAR': datetime.now().year,
        'IS_DEBUG': settings.DEBUG,
    }
