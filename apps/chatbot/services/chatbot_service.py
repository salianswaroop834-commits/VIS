import re
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import PermissionDenied

from apps.chatbot.models import ChatSession, ChatMessage, ChatbotToolCall, MessageSender
from apps.policies.models import Policy, PolicyStatus
from apps.claims.models import Claim, ClaimStatus
from apps.claims.services.claim_service import ClaimService
from apps.vehicles.models import Vehicle
from apps.quotations.models import QuotationDraft
from apps.service_requests.models import ServiceRequest, ServiceRequestType
from apps.service_requests.services.service_request_service import ServiceRequestService
from apps.customers.models import CustomerProfile
from apps.rag.services.rag_service import RagService
from apps.audit.services.audit_service import AuditService
from core.services import ServiceValidationError
from apps.chatbot.services.llm_provider import get_llm_provider


class ChatbotGuardrailViolation(Exception):
    """Raised when user message violates security, prompt-injection, or role boundaries."""
    pass


class ChatbotService:
    """
    Stateful conversational agent engine for Nexisure Vehicle Insurance:
    1. Multi-turn session persistence and context window tracking with strict ownership isolation.
    2. Prompt-injection defense and safety guardrail enforcement against arbitrary SQL and rule bypasses.
    3. RAG semantic knowledge retrieval integration grounded in approved documents.
    4. Controlled transactional tool calling strictly invoking existing Django service layers.
    5. Strict prohibition against automated claim decisions (human-in-the-loop mandatory).
    """

    INJECTION_PATTERNS = [
        r'ignore\s+(all\s+)?(previous|prior)\s+instructions',
        r'system\s+prompt',
        r'override\s+(security|validation|database|guardrail)',
        r'drop\s+table',
        r'grant\s+(me\s+)?(admin|administrator|root)',
        r'bypass\s+auth(orization)?',
        r'leak\s+(password|secret|key|token)',
        r'jailbreak',
        r'select\s+.*\s+from\s+',
        r'delete\s+from',
        r'union\s+select',
    ]

    CLAIM_DECISION_PATTERNS = [
        r'approve\s+(my\s+)?claim',
        r'reject\s+(this\s+|my\s+)?claim',
        r'change\s+settlement',
        r'override\s+decision',
        r'settle\s+(my\s+)?claim\s+now',
    ]

    @classmethod
    def get_or_create_session(cls, session_key: str, user=None) -> ChatSession:
        """
        Retrieves or initializes a chat session.
        Strictly enforces user ownership: authenticated users cannot hijack another user's session.
        """
        if not session_key:
            session_key = uuid.uuid4().hex

        session, created = ChatSession.objects.get_or_create(
            session_key=session_key,
            defaults={'user': user if user and user.is_authenticated else None}
        )

        # Ownership validation: block cross-user access
        if session.user and user and user.is_authenticated and session.user != user:
            raise PermissionDenied("Access Denied: You cannot access another user's chat session.")

        # Update user binding if previously guest and user just logged in
        if user and user.is_authenticated and session.user is None:
            session.user = user
            session.save(update_fields=['user', 'updated_at'])

        return session

    @classmethod
    def check_guardrails(cls, text: str) -> Optional[str]:
        """
        Scans input for prompt injections, privilege escalation, or unsafe commands.
        Returns a rejection reason if a violation is detected, or None if safe.
        """
        lower = text.lower()
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, lower):
                return (
                    "Security Notice: Your message triggered an automated safety guardrail "
                    "against prompt injection or unauthorized system instructions. "
                    "This event has been logged for compliance monitoring."
                )

        for pattern in cls.CLAIM_DECISION_PATTERNS:
            if re.search(pattern, lower):
                return (
                    "Claim Decision Restriction: The AI assistant is strictly prohibited from "
                    "approving, rejecting, or altering settlements on insurance claims. "
                    "All claim adjudications require formal review and decision by an authorized human claims handler."
                )

        return None

    @classmethod
    def get_my_policies(cls, user) -> Dict[str, Any]:
        """Tool 1: Read-only retrieval of caller's active vehicle insurance policies."""
        if not user or not user.is_authenticated:
            return {
                'success': False,
                'message': "Authentication required: Please log in to view your vehicle policies.",
                'policies': [],
            }

        customer = getattr(user, 'customer_profile', None)
        if not customer:
            return {
                'success': False,
                'message': "No customer profile found associated with your account.",
                'policies': [],
            }

        policies = Policy.objects.filter(customer=customer, status=PolicyStatus.ACTIVE).select_related('vehicle', 'coverage_plan')
        if not policies.exists():
            return {
                'success': True,
                'message': "You do not have any active vehicle policies registered with Nexisure.",
                'policies': [],
            }

        data = [
            {
                'policy_number': p.policy_number,
                'plan_name': p.coverage_plan.name,
                'vehicle_plate': p.vehicle.registration_number,
                'vehicle_model': f"{p.vehicle.make} {p.vehicle.model} ({p.vehicle.manufacture_year})",
                'status': p.status,
                'valid_until': str(p.end_date),
                'idv': float(p.vehicle.vehicle_value),
                'deductible': float(p.deductible_amount),
            }
            for p in policies
        ]
        return {
            'success': True,
            'message': f"Found {len(data)} active policy record(s) under your profile.",
            'policies': data,
        }

    @classmethod
    def get_my_vehicles(cls, user) -> Dict[str, Any]:
        """Tool 2: Read-only retrieval of caller's registered vehicles."""
        if not user or not user.is_authenticated:
            return {
                'success': False,
                'message': "Authentication required: Please log in to view your vehicles.",
                'vehicles': [],
            }

        customer = getattr(user, 'customer_profile', None)
        if not customer:
            return {
                'success': False,
                'message': "No customer profile found associated with your account.",
                'vehicles': [],
            }

        vehicles = Vehicle.objects.filter(customer=customer)
        data = [
            {
                'registration_number': v.registration_number,
                'make_model': f"{v.make} {v.model}",
                'year': v.manufacture_year,
                'vehicle_type': v.get_vehicle_type_display(),
                'fuel_type': v.get_fuel_type_display(),
                'idv': float(v.vehicle_value),
            }
            for v in vehicles
        ]
        return {
            'success': True,
            'message': f"Found {len(data)} registered vehicle(s) under your profile.",
            'vehicles': data,
        }

    @classmethod
    def get_my_service_requests(cls, user) -> Dict[str, Any]:
        """Tool 3: Read-only retrieval of caller's policy service requests."""
        if not user or not user.is_authenticated:
            return {
                'success': False,
                'message': "Authentication required: Please log in to view your service requests.",
                'service_requests': [],
            }

        customer = getattr(user, 'customer_profile', None)
        if not customer:
            return {
                'success': False,
                'message': "No customer profile found associated with your account.",
                'service_requests': [],
            }

        requests = ServiceRequest.objects.filter(customer=customer)
        data = [
            {
                'request_number': sr.request_number,
                'request_type': sr.get_request_type_display(),
                'title': sr.title,
                'status': sr.get_status_display(),
                'created_at': sr.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for sr in requests
        ]
        return {
            'success': True,
            'message': f"Found {len(data)} service request(s) under your profile.",
            'service_requests': data,
        }

    @classmethod
    def get_my_quotations(cls, user) -> Dict[str, Any]:
        """Tool 4: Read-only retrieval of caller's quotations."""
        if not user or not user.is_authenticated:
            return {
                'success': False,
                'message': "Authentication required: Please log in to view your quotations.",
                'quotations': [],
            }

        customer = getattr(user, 'customer_profile', None)
        if not customer:
            return {
                'success': False,
                'message': "No customer profile found associated with your account.",
                'quotations': [],
            }

        quotes = QuotationDraft.objects.filter(customer=customer).select_related('coverage_plan')
        data = [
            {
                'quote_number': q.quotation_number,
                'plan': q.coverage_plan.name if q.coverage_plan else 'Not Selected',
                'status': q.status,
                'premium': float(q.calculated_premium) if q.calculated_premium else 0.0,
                'valid_until': str(q.valid_until) if q.valid_until else 'N/A',
            }
            for q in quotes
        ]
        return {
            'success': True,
            'message': f"Found {len(data)} quotation record(s) under your profile.",
            'quotations': data,
        }

    @classmethod
    def check_claim_status(cls, claim_number: str, user) -> Dict[str, Any]:
        """Tool 5: Read-only claim status lookup with strict ownership validation."""
        if not user or not user.is_authenticated:
            return {
                'success': False,
                'message': "Authentication required: Please log in to check your claim status.",
            }

        try:
            claim = Claim.objects.select_related('policy__customer__user', 'policy__vehicle').get(
                claim_number__iexact=claim_number.strip()
            )
        except Claim.DoesNotExist:
            return {
                'success': False,
                'message': f"Claim number '{claim_number}' was not found in the Nexisure registry.",
            }

        # Ownership authorization check
        is_staff = getattr(user, 'is_staff', False) or getattr(user, 'role', '') in ['UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR']
        if claim.policy.customer.user != user and not is_staff:
            return {
                'success': False,
                'message': "Access Denied: You are not authorized to view claim records belonging to other policyholders.",
            }

        return {
            'success': True,
            'claim_number': claim.claim_number,
            'policy_number': claim.policy.policy_number,
            'vehicle': claim.policy.vehicle.registration_number,
            'status': claim.status,
            'claimed_amount': float(claim.estimated_loss_amount),
            'approved_amount': float(claim.settlement_amount) if claim.settlement_amount else 0.0,
            'created_at': claim.created_at.strftime('%Y-%m-%d %H:%M'),
            'handler': claim.handler.user.get_full_name() if claim.handler else "Pending Shared Queue Assignment",
        }

    @classmethod
    def prepare_claim_registration(
        cls,
        session: ChatSession,
        user,
        policy_number: str,
        incident_date_str: str,
        estimated_amount: float,
        description: str,
        location: str = "Unspecified Incident Location"
    ) -> Dict[str, Any]:
        """
        Tool 6 (Step 1 of 2): Stages claim registration for explicit customer confirmation.
        Does NOT modify policy/claim state until the customer confirms.
        """
        if not user or not user.is_authenticated:
            return {
                'success': False,
                'message': "Please log in to your Nexisure customer portal before registering a claim.",
            }

        customer = getattr(user, 'customer_profile', None)
        if not customer:
            return {
                'success': False,
                'message': "Customer profile not found. Please contact support.",
            }

        try:
            policy = Policy.objects.get(policy_number__iexact=policy_number.strip(), customer=customer)
        except Policy.DoesNotExist:
            return {
                'success': False,
                'message': f"Active policy '{policy_number}' was not found in your customer account.",
            }

        if policy.status != PolicyStatus.ACTIVE:
            return {
                'success': False,
                'message': f"Policy '{policy_number}' is {policy.status}. Claims can only be filed against ACTIVE policies.",
            }

        # Stage transaction payload
        pending_payload = {
            'action': 'REGISTER_CLAIM',
            'policy_id': str(policy.id),
            'policy_number': policy.policy_number,
            'vehicle_plate': policy.vehicle.registration_number,
            'incident_date': incident_date_str,
            'estimated_amount': float(estimated_amount),
            'description': description,
            'location': location,
            'staged_at': timezone.now().isoformat(),
        }

        session.pending_transaction = pending_payload
        session.save(update_fields=['pending_transaction', 'updated_at'])

        # Record proposed tool call
        ChatbotToolCall.objects.create(
            session=session,
            tool_name='register_claim',
            parameters=pending_payload,
            execution_status=ChatbotToolCall.ExecutionStatus.PROPOSED,
        )

        return {
            'success': True,
            'requires_confirmation': True,
            'message': (
                f"I have prepared your claim registration for Policy **{policy.policy_number}** "
                f"({policy.vehicle.registration_number}) for estimated damage of **₹{estimated_amount:,.2f}**.\n\n"
                f"**Please confirm:** Reply with '**CONFIRM**' to submit this claim into the adjudication queue, "
                f"or '**CANCEL**' to abort."
            ),
            'staged_data': pending_payload,
        }

    @classmethod
    def confirm_transaction(cls, session: ChatSession, user) -> Dict[str, Any]:
        """
        Tool 7 (Step 2 of 2): Executes the pending staged transaction upon explicit customer confirmation.
        """
        pending = session.pending_transaction
        if not pending:
            return {
                'success': False,
                'message': "There is no pending transaction awaiting confirmation in this session.",
            }

        action = pending.get('action')
        if action == 'REGISTER_CLAIM':
            try:
                customer = getattr(user, 'customer_profile', None)
                policy = Policy.objects.get(id=pending['policy_id'])

                try:
                    dt = datetime.strptime(pending['incident_date'], '%Y-%m-%d')
                    inc_date = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
                except Exception:
                    inc_date = timezone.now()

                # Call backend business service
                claim = ClaimService.file_claim(
                    customer=customer,
                    policy=policy,
                    incident_date=inc_date,
                    incident_location=pending.get('location', 'Unspecified Location'),
                    incident_description=pending.get('description', 'Reported via AI Assistant'),
                    estimated_loss_amount=Decimal(str(pending['estimated_amount'])),
                )

                ChatbotToolCall.objects.filter(
                    session=session,
                    tool_name='register_claim',
                    execution_status=ChatbotToolCall.ExecutionStatus.PROPOSED
                ).update(
                    execution_status=ChatbotToolCall.ExecutionStatus.EXECUTED,
                    result_payload={'claim_number': claim.claim_number, 'claim_id': str(claim.id)}
                )

                AuditService.log(
                    action='CHATBOT_TOOL_EXECUTED',
                    target_entity='Claim',
                    target_id=str(claim.id),
                    actor=user,
                    details={
                        'tool': 'register_claim',
                        'claim_number': claim.claim_number,
                        'session_key': session.session_key,
                    }
                )

                session.pending_transaction = None
                session.save(update_fields=['pending_transaction', 'updated_at'])

                return {
                    'success': True,
                    'message': (
                        f"Your claim has been successfully registered under Claim Reference **{claim.claim_number}**! "
                        f"It is now in the shared queue awaiting independent surveyor and claims handler assignment. "
                        f"You can track its status anytime in your portal or by asking me."
                    ),
                    'claim_number': claim.claim_number,
                }
            except Exception as e:
                return {
                    'success': False,
                    'message': f"Claim registration failed: {str(e)}",
                }

        return {
            'success': False,
            'message': f"Unknown pending action: {action}",
        }

    @classmethod
    def cancel_transaction(cls, session: ChatSession) -> Dict[str, Any]:
        """Cancels any staged pending transaction."""
        if not session.pending_transaction:
            return {
                'success': True,
                'message': "No pending transaction to cancel.",
            }

        session.pending_transaction = None
        session.save(update_fields=['pending_transaction', 'updated_at'])

        ChatbotToolCall.objects.filter(
            session=session,
            execution_status=ChatbotToolCall.ExecutionStatus.PROPOSED
        ).update(execution_status=ChatbotToolCall.ExecutionStatus.BLOCKED, guardrail_notes='Cancelled by user')

        return {
            'success': True,
            'message': "The pending transaction has been cancelled. How else may I assist you today?",
        }

    @classmethod
    def process_user_message(cls, session_key: str, user_input: str, user=None) -> Dict[str, Any]:
        """
        Main conversational dispatcher:
        1. Logs user message to database.
        2. Evaluates prompt injection guardrails.
        3. Manages two-step confirmation state.
        4. Invokes transactional tools or RAG knowledge retrieval.
        5. Logs and returns assistant response with citations and disclaimers.
        """
        session = cls.get_or_create_session(session_key, user=user)
        cleaned_text = user_input.strip()

        # 1. Log incoming user message
        ChatMessage.objects.create(
            session=session,
            sender=MessageSender.USER,
            content=cleaned_text,
        )

        # 2. Guardrail Scan
        violation = cls.check_guardrails(cleaned_text)
        if violation:
            AuditService.log(
                action='CHATBOT_TOOL_EXECUTED',
                target_entity='ChatSession',
                target_id=str(session.id),
                actor=user,
                is_success=False,
                details={'guardrail_violation': violation, 'input': cleaned_text},
            )
            ChatMessage.objects.create(
                session=session,
                sender=MessageSender.ASSISTANT,
                content=violation,
            )
            return {
                'message': violation,
                'sources': [],
                'tool_executed': None,
                'pending_transaction': None,
                'is_guardrail_blocked': True,
            }

        # 3. Handle Two-Step Confirmation / Cancellation
        lower_text = cleaned_text.lower()
        if session.pending_transaction:
            if lower_text in ['confirm', 'yes', 'confirm claim', 'yes confirm']:
                res = cls.confirm_transaction(session, user)
                resp_text = res['message']
                ChatMessage.objects.create(session=session, sender=MessageSender.ASSISTANT, content=resp_text)
                return {
                    'message': resp_text,
                    'sources': [],
                    'tool_executed': 'confirm_transaction',
                    'pending_transaction': None,
                }
            elif lower_text in ['cancel', 'no', 'abort', 'stop']:
                res = cls.cancel_transaction(session)
                resp_text = res['message']
                ChatMessage.objects.create(session=session, sender=MessageSender.ASSISTANT, content=resp_text)
                return {
                    'message': resp_text,
                    'sources': [],
                    'tool_executed': 'cancel_transaction',
                    'pending_transaction': None,
                }

        # 4. Pattern / Intent Routing
        tool_executed = None
        sources = []

        # Intent A: List caller's policies
        if 'polic' in lower_text and any(phrase in lower_text for phrase in ['my', 'view', 'show', 'list', 'active', 'check', 'get']):
            tool_executed = 'get_my_policies'
            p_res = cls.get_my_policies(user)
            if not p_res['success']:
                resp_text = p_res['message']
            else:
                policies_lines = [
                    f"&bull; **{p['policy_number']}** ({p['plan_name']}) &mdash; Vehicle: {p['vehicle_plate']} ({p['vehicle_model']}), Valid until: {p['valid_until']}, IDV: ₹{p['idv']:,.2f}, Deductible: ₹{p['deductible']:,.2f}"
                    for p in p_res['policies']
                ]
                resp_text = f"{p_res['message']}\n\n" + "\n".join(policies_lines)

        # Intent B: List caller's vehicles
        elif 'vehicle' in lower_text and any(term in lower_text for term in ['my', 'registered', 'list', 'show', 'view']):
            tool_executed = 'get_my_vehicles'
            v_res = cls.get_my_vehicles(user)
            if not v_res['success']:
                resp_text = v_res['message']
            else:
                veh_lines = [
                    f"&bull; **{v['registration_number']}** &mdash; {v['make_model']} ({v['year']}), Type: {v['vehicle_type']}, IDV: ₹{v['idv']:,.2f}"
                    for v in v_res['vehicles']
                ]
                resp_text = f"{v_res['message']}\n\n" + "\n".join(veh_lines)

        # Intent C: List caller's service requests
        elif any(term in lower_text for term in ['service request', 'my tickets', 'servicing status']):
            tool_executed = 'get_my_service_requests'
            sr_res = cls.get_my_service_requests(user)
            if not sr_res['success']:
                resp_text = sr_res['message']
            else:
                sr_lines = [
                    f"&bull; **{sr['request_number']}** &mdash; {sr['title']} ({sr['request_type']}) &mdash; Status: {sr['status']}"
                    for sr in sr_res['service_requests']
                ]
                resp_text = f"{sr_res['message']}\n\n" + "\n".join(sr_lines)

        # Intent C2: List caller's quotations
        elif 'quotation' in lower_text or 'quote' in lower_text:
            tool_executed = 'get_my_quotations'
            q_res = cls.get_my_quotations(user)
            if not q_res['success']:
                resp_text = q_res['message']
            else:
                q_lines = [
                    f"&bull; **{q['quote_number']}** &mdash; Plan: {q['plan']}, Status: {q['status']}, Premium: ₹{q['premium']:,.2f}, Valid until: {q['valid_until']}"
                    for q in q_res['quotations']
                ]
                resp_text = f"{q_res['message']}\n\n" + "\n".join(q_lines)

        # Intent D: Check Claim Status
        elif 'claim' in lower_text and any(term in lower_text for term in ['status', 'check claim', 'track claim']):
            match = re.search(r'(CLM-[0-9]{4}-[A-Z0-9]+)', cleaned_text, re.IGNORECASE)
            if match:
                claim_num = match.group(1).upper()
                c_res = cls.check_claim_status(claim_num, user)
                tool_executed = 'check_claim_status'
                if not c_res['success']:
                    resp_text = c_res['message']
                else:
                    resp_text = (
                        f"**Claim Record: {c_res['claim_number']}**\n"
                        f"&bull; Policy: {c_res['policy_number']} ({c_res['vehicle']})\n"
                        f"&bull; Adjudication Status: **{c_res['status']}**\n"
                        f"&bull; Claimed Amount: ₹{c_res['claimed_amount']:,.2f}\n"
                        f"&bull; Approved Settlement: ₹{c_res['approved_amount']:,.2f}\n"
                        f"&bull; Handler: {c_res['handler']}\n"
                        f"&bull; Filed At: {c_res['created_at']}"
                    )
            else:
                resp_text = "To track a claim, please provide your Claim Number (e.g. `CLM-2026-ABC12345`)."

        # Intent E: Claim Filing Initiation
        elif any(phrase in lower_text for phrase in ['file claim', 'register claim', 'file a claim', 'accident claim', 'new claim']):
            p_res = cls.get_my_policies(user)
            if not p_res['success'] or not p_res.get('policies'):
                resp_text = p_res.get('message', 'Please log in to your account with an active policy to register a claim.')
            else:
                user_policies = p_res['policies']
                first_policy = user_policies[0]
                res = cls.prepare_claim_registration(
                    session=session,
                    user=user,
                    policy_number=first_policy['policy_number'],
                    incident_date_str=timezone.now().strftime('%Y-%m-%d'),  # UTC date to avoid timezone boundary issues
                    estimated_amount=15000.0,
                    description="Customer initiated accident report via AI Assistant.",
                )
                tool_executed = 'prepare_claim_registration'
                resp_text = res['message']

        # Intent F: RAG Knowledge Base Retrieval (Default)
        else:
            rag_res = RagService.answer_query(cleaned_text)
            resp_text = rag_res['answer']
            sources = rag_res['sources']
            tool_executed = 'rag_retrieval'

        # 5. Save and return assistant response
        ChatMessage.objects.create(
            session=session,
            sender=MessageSender.ASSISTANT,
            content=resp_text,
            sources=sources,
        )

        return {
            'message': resp_text,
            'sources': sources,
            'tool_executed': tool_executed,
            'pending_transaction': session.pending_transaction,
            'session_key': session.session_key,
        }
