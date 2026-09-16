from django.views.generic import ListView, DetailView
from django.http import Http404
from core.permissions import AdminRequiredMixin
from .models import AuditLog, AuditAction
from .selectors import get_audit_logs_queryset, get_audit_log_by_id


class AuditLogListView(AdminRequiredMixin, ListView):
    """
    Immutable compliance audit ledger view for administrators.
    Allows searching and filtering by action, actor, and target entity.
    """
    model = AuditLog
    template_name = 'audit/audit_list.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        action = self.request.GET.get('action')
        actor_email = self.request.GET.get('actor')
        target_entity = self.request.GET.get('target_entity')
        search = self.request.GET.get('q')

        return get_audit_logs_queryset(
            action=action,
            actor_email=actor_email,
            target_entity=target_entity,
            search=search,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action_choices'] = AuditAction.choices
        context['selected_action'] = self.request.GET.get('action', '')
        context['actor_query'] = self.request.GET.get('actor', '')
        context['entity_query'] = self.request.GET.get('target_entity', '')
        context['search_query'] = self.request.GET.get('q', '')
        return context


class AuditLogDetailView(AdminRequiredMixin, DetailView):
    model = AuditLog
    template_name = 'audit/audit_detail.html'
    context_object_name = 'log'

    def get_object(self, queryset=None):
        pk = self.kwargs.get('pk')
        log = get_audit_log_by_id(pk)
        if not log:
            raise Http404("Audit log entry not found.")
        return log
