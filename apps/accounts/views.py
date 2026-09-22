from django.shortcuts import render, redirect
from django.views.generic import TemplateView, View
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.accounts.services.supabase_auth import SupabaseAuthService
from apps.customers.models import CustomerProfile
from core.services import DataNormalizer
from apps.audit.models import AuditAction
from apps.audit.services.audit_service import AuditService


def redirect_user_by_role(user: User) -> str:
    """Redirects authenticated user to their designated portal dashboard."""
    if user.is_customer:
        return reverse('customers:dashboard')
    elif user.is_underwriter:
        return reverse('staff:underwriter-dashboard')
    elif user.is_claims_handler:
        return reverse('staff:claims-handler-dashboard')
    elif user.is_administrator:
        return reverse('staff:admin-dashboard')
    return reverse('home')


class LoginView(View):
    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(redirect_user_by_role(request.user))
        return render(request, self.template_name)

    def post(self, request):
        email = DataNormalizer.normalize_email(request.POST.get('email', ''))
        password = request.POST.get('password', '')

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, self.template_name)

        # Authenticate using email as username
        user = authenticate(request, username=email, password=password)
        if user is None:
            # Also attempt lookup by email directly
            user_obj = User.objects.filter(email=email).first()
            if user_obj and user_obj.check_password(password):
                user = user_obj

        if user and user.is_active:
            login(request, user)
            AuditService.log(
                action=AuditAction.USER_LOGIN,
                target_entity='User',
                target_id=str(user.pk),
                actor=user,
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'email': user.email, 'role': user.role, 'method': 'password'}
            )
            messages.success(request, f"Welcome back, {user.email}!")
            next_url = request.GET.get('next') or request.POST.get('next')
            return redirect(next_url or redirect_user_by_role(user))
        else:
            messages.error(request, "Invalid email or password. You can also sign in using Email OTP.")
            return render(request, self.template_name, {'email': email})


class RegisterView(View):
    template_name = 'accounts/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(redirect_user_by_role(request.user))
        return render(request, self.template_name)

    def post(self, request):
        email = DataNormalizer.normalize_email(request.POST.get('email', ''))
        first_name = DataNormalizer.normalize_text(request.POST.get('first_name', ''))
        last_name = DataNormalizer.normalize_text(request.POST.get('last_name', ''))
        phone_number = DataNormalizer.normalize_phone(request.POST.get('phone_number', ''))
        password = request.POST.get('password', '')

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, self.template_name)

        if User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists. Please sign in.")
            return redirect('accounts:login')

        username = email.split('@')[0]
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role=UserRole.CUSTOMER,
            email_verified=False,
        )

        # Automatically create CustomerProfile
        cust_code = f"CUST-{user.id.hex[:8].upper()}"
        cust_profile = CustomerProfile.objects.create(
            user=user,
            customer_code=cust_code,
        )

        AuditService.log(
            action=AuditAction.CUSTOMER_CREATED,
            target_entity='CustomerProfile',
            target_id=str(cust_profile.pk),
            actor=user,
            details={'customer_code': cust_code, 'email': user.email}
        )

        login(request, user)
        messages.success(request, "Account created successfully! Welcome to Nexisure.")
        return redirect('customers:dashboard')


class OtpRequestView(View):
    """Initiates dispatch of an Email One-Time Passcode with cooldown rate-limiting."""
    COOLDOWN_SECONDS = 30

    def post(self, request):
        import time
        email = DataNormalizer.normalize_email(request.POST.get('email', ''))
        if not email:
            messages.error(request, "Please enter your email to receive an OTP.")
            return redirect('accounts:verify-otp')

        # Server-side cooldown rate-limiting against repeatedly requesting OTPs
        last_request_time = request.session.get('last_otp_request_at')
        now_ts = time.time()
        if last_request_time and (now_ts - last_request_time < self.COOLDOWN_SECONDS):
            remaining = int(self.COOLDOWN_SECONDS - (now_ts - last_request_time))
            messages.warning(request, f"Please wait {remaining} seconds before requesting another verification code.")
            return redirect('accounts:verify-otp')

        result = SupabaseAuthService.send_otp(email)
        if result.get('success'):
            request.session['pending_otp_email'] = email
            request.session['last_otp_request_at'] = now_ts
            request.session['otp_attempts'] = 0  # Reset attempt counter on fresh code dispatch
            messages.success(
                request,
                result.get('message', 'A 6-digit verification code has been dispatched to your email address. Please check your inbox.')
            )
            return redirect('accounts:verify-otp')
        else:
            messages.error(request, result.get('message', 'Failed to dispatch verification code.'))
            if request.session.get('pending_otp_email'):
                return redirect('accounts:verify-otp')
            return redirect('accounts:login')


class OtpVerifyView(View):
    template_name = 'accounts/verify_otp.html'
    MAX_ATTEMPTS = 5

    def get(self, request):
        if request.GET.get('change_email') == '1':
            request.session.pop('pending_otp_email', None)
            request.session.pop('otp_attempts', None)
            request.session.pop('last_otp_request_at', None)
            email = ''
        else:
            email = request.session.get('pending_otp_email', '')
        return render(request, self.template_name, {'email': email})

    def post(self, request):
        email = DataNormalizer.normalize_email(request.POST.get('email', '')) or request.session.get('pending_otp_email', '')
        otp_code = request.POST.get('otp_code', '').strip()

        if not email:
            messages.error(request, "Email address is required to verify your passcode.")
            return redirect('accounts:verify-otp')

        # Prevent brute-force attempts: Check attempt threshold
        attempts = request.session.get('otp_attempts', 0)
        if attempts >= self.MAX_ATTEMPTS:
            messages.error(
                request,
                f"Maximum verification attempts exceeded ({self.MAX_ATTEMPTS}/{self.MAX_ATTEMPTS}). "
                "For security purposes, please request a new security code."
            )
            return render(request, self.template_name, {'email': email})

        # Validate that candidate OTP is exactly 6 numeric digits before calling service
        if not otp_code or not otp_code.isdigit() or len(otp_code) != 6:
            request.session['otp_attempts'] = attempts + 1
            remaining = max(0, self.MAX_ATTEMPTS - request.session['otp_attempts'])
            messages.error(
                request,
                f"Please enter a valid 6-digit numeric passcode. ({remaining} attempt(s) remaining)"
            )
            return render(request, self.template_name, {'email': email})

        result = SupabaseAuthService.verify_otp(email, otp_code)
        if result.get('success') and result.get('user'):
            user = result['user']
            # Authenticate Django user session
            login(request, user)
            AuditService.log(
                action=AuditAction.USER_LOGIN,
                target_entity='User',
                target_id=str(user.pk),
                actor=user,
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'email': user.email, 'role': user.role, 'method': 'otp'}
            )

            # Securely store Supabase tokens in session if available
            if result.get('access_token'):
                request.session['supabase_access_token'] = result['access_token']
            if result.get('refresh_token'):
                request.session['supabase_refresh_token'] = result['refresh_token']
            if getattr(user, 'supabase_uid', None):
                request.session['supabase_user_id'] = str(user.supabase_uid)

            # Cleanup transient verification session data
            request.session.pop('pending_otp_email', None)
            request.session.pop('otp_attempts', None)
            request.session.pop('last_otp_request_at', None)

            messages.success(request, f"Successfully signed in as {user.email}.")
            return redirect(redirect_user_by_role(user))
        else:
            request.session['otp_attempts'] = attempts + 1
            remaining = max(0, self.MAX_ATTEMPTS - request.session['otp_attempts'])
            if remaining == 0:
                err_msg = (
                    f"Maximum verification attempts exceeded ({self.MAX_ATTEMPTS}/{self.MAX_ATTEMPTS}). "
                    "Please request a new passcode."
                )
            else:
                base_err = result.get('message', 'Invalid or expired passcode.')
                err_msg = f"{base_err} ({remaining} attempt(s) remaining)"

            messages.error(request, err_msg)
            return render(request, self.template_name, {'email': email})


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'


class LogoutView(View):
    def get(self, request):
        if request.user.is_authenticated:
            AuditService.log(
                action=AuditAction.USER_LOGOUT,
                target_entity='User',
                target_id=str(request.user.pk),
                actor=request.user,
                details={'email': request.user.email}
            )
        logout(request)
        messages.info(request, "You have been securely signed out.")
        return redirect('home')

    def post(self, request):
        if request.user.is_authenticated:
            AuditService.log(
                action=AuditAction.USER_LOGOUT,
                target_entity='User',
                target_id=str(request.user.pk),
                actor=request.user,
                details={'email': request.user.email}
            )
        logout(request)
        messages.info(request, "You have been securely signed out.")
        return redirect('home')
