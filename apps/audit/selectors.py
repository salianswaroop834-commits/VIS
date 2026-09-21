from typing import Optional
from django.db.models import QuerySet, Q
from apps.audit.models import AuditLog, AuditAction


def get_audit_logs_queryset(
    action: Optional[str] = None,
    actor_email: Optional[str] = None,
    target_entity: Optional[str] = None,
    search: Optional[str] = None,
) -> QuerySet[AuditLog]:
    """
    Returns a filtered queryset of AuditLog records ordered by creation time descending.
    Encapsulates audit queries away from views.
    """
    qs = AuditLog.objects.all().select_related('actor').order_by('-created_at')

    if action and action in AuditAction.values:
        qs = qs.filter(action=action)

    if actor_email:
        qs = qs.filter(actor_email__icontains=actor_email.strip())

    if target_entity:
        qs = qs.filter(target_entity__iexact=target_entity.strip())

    if search:
        s = search.strip()
        qs = qs.filter(
            Q(target_id__icontains=s) |
            Q(actor_email__icontains=s) |
            Q(action__icontains=s) |
            Q(target_entity__icontains=s)
        )

    return qs


def get_audit_log_by_id(log_id: str) -> Optional[AuditLog]:
    """Retrieves an individual AuditLog by UUID PK."""
    try:
        return AuditLog.objects.select_related('actor').filter(pk=log_id).first()
    except Exception:
        return None
