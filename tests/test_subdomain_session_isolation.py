"""
Automated Session-Isolation Test Suite (Requirements A through J).

Validates subdomain-based session isolation across:
  - Tab 1: customer.localhost:8000
  - Tab 2: staff.localhost:8000
  - Tab 3: admin.localhost:8000

Ensures:
  - RFC 6265 host-only cookie isolation prevents cross-subdomain session overwrite
  - Demo accounts (Customer, Underwriter Staff, Admin) maintain independent concurrent sessions
  - Role-based access control (RBAC) boundaries are strictly enforced
  - CSRF protection and OTP authentication remain fully operative on subdomains
"""

import pytest
from decimal import Decimal
from django.test import Client, TestCase
from django.urls import reverse
from django.conf import settings
from django.core.management import call_command
from accounts.models import User, UserRole
from customers.models import CustomerProfile
from staff.models import StaffProfile


@pytest.mark.django_db
class TestSubdomainSessionIsolation:
    """
    Comprehensive automated test suite covering Requirements A through J
    for subdomain-based multi-role session isolation.
    """

    @pytest.fixture(autouse=True)
    def setup_demo_data(self):
        """Seed demo accounts and baseline data."""
        call_command('seed_demo_data')
        self.customer_user = User.objects.get(email='customer@nexisure.test')
        self.underwriter_user = User.objects.get(email='underwriter@nexisure.test')
        self.admin_user = User.objects.get(email='admin@nexisure.test')

    def test_configuration_subdomain_settings(self):
        """
        Verify that ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, and SESSION_COOKIE_DOMAIN
        are correctly configured for host-only subdomain session isolation.
        """
        # 1. ALLOWED_HOSTS checks
        assert any('.localhost' in h for h in settings.ALLOWED_HOSTS) or 'customer.localhost' in settings.ALLOWED_HOSTS
        assert 'customer.localhost' in settings.ALLOWED_HOSTS or '.localhost' in settings.ALLOWED_HOSTS
        assert 'staff.localhost' in settings.ALLOWED_HOSTS or '.localhost' in settings.ALLOWED_HOSTS
        assert 'admin.localhost' in settings.ALLOWED_HOSTS or '.localhost' in settings.ALLOWED_HOSTS

        # 2. CSRF_TRUSTED_ORIGINS checks
        csrf_origins_str = " ".join(settings.CSRF_TRUSTED_ORIGINS)
        assert 'http://*.localhost:8000' in settings.CSRF_TRUSTED_ORIGINS or 'http://customer.localhost:8000' in csrf_origins_str
        assert 'customer.localhost:8000' in csrf_origins_str
        assert 'staff.localhost:8000' in csrf_origins_str
        assert 'admin.localhost:8000' in csrf_origins_str

        # 3. Host-Only Cookie Isolation check:
        # When SESSION_COOKIE_DOMAIN is None, browsers enforce RFC 6265 host-only scoping
        assert getattr(settings, 'SESSION_COOKIE_DOMAIN', None) is None

    def test_requirement_a_customer_remains_customer_after_staff_login(self):
        """
        Requirement A: Customer remains Customer after Staff logs in.
        Tab 1 (customer.localhost:8000) logged in as Customer.
        Tab 2 (staff.localhost:8000) logged in as Staff.
        Tab 1 still retains Customer session and identity.
        """
        customer_client = Client(HTTP_HOST='customer.localhost:8000')
        staff_client = Client(HTTP_HOST='staff.localhost:8000')

        # 1. Customer logs in on customer.localhost
        login_res_cust = customer_client.post(reverse('accounts:login'), {
            'email': 'customer@nexisure.test',
            'password': 'DemoCust@2026',
        })
        assert login_res_cust.status_code in (302, 200)

        # Confirm Customer identity in Tab 1
        resp_cust1 = customer_client.get(reverse('customers:dashboard'))
        assert resp_cust1.status_code == 200
        assert resp_cust1.wsgi_request.user.is_authenticated
        assert resp_cust1.wsgi_request.user.email == 'customer@nexisure.test'
        assert resp_cust1.wsgi_request.user.role == UserRole.CUSTOMER

        # 2. Staff logs in on staff.localhost
        login_res_staff = staff_client.post(reverse('accounts:login'), {
            'email': 'underwriter@nexisure.test',
            'password': 'DemoStaff@2026',
        })
        assert login_res_staff.status_code in (302, 200)

        # Confirm Staff identity in Tab 2
        resp_staff = staff_client.get(reverse('staff:underwriter-dashboard'))
        assert resp_staff.status_code == 200
        assert resp_staff.wsgi_request.user.is_authenticated
        assert resp_staff.wsgi_request.user.email == 'underwriter@nexisure.test'
        assert resp_staff.wsgi_request.user.role == UserRole.UNDERWRITER

        # 3. Verify Tab 1 STILL remains Customer (no session overwrite)
        resp_cust_after = customer_client.get(reverse('customers:dashboard'))
        assert resp_cust_after.status_code == 200
        assert resp_cust_after.wsgi_request.user.is_authenticated
        assert resp_cust_after.wsgi_request.user.email == 'customer@nexisure.test'
        assert resp_cust_after.wsgi_request.user.role == UserRole.CUSTOMER

    def test_requirement_b_staff_remains_staff_after_admin_login(self):
        """
        Requirement B: Staff remains Staff after Admin logs in.
        Tab 2 (staff.localhost:8000) logged in as Staff.
        Tab 3 (admin.localhost:8000) logged in as Admin.
        Tab 2 still retains Staff session and identity.
        """
        staff_client = Client(HTTP_HOST='staff.localhost:8000')
        admin_client = Client(HTTP_HOST='admin.localhost:8000')

        # 1. Staff logs in on staff.localhost
        staff_client.post(reverse('accounts:login'), {
            'email': 'underwriter@nexisure.test',
            'password': 'DemoStaff@2026',
        })
        resp_staff1 = staff_client.get(reverse('staff:underwriter-dashboard'))
        assert resp_staff1.status_code == 200
        assert resp_staff1.wsgi_request.user.email == 'underwriter@nexisure.test'

        # 2. Admin logs in on admin.localhost
        admin_client.post(reverse('accounts:login'), {
            'email': 'admin@nexisure.test',
            'password': 'DemoAdmin@2026',
        })
        resp_admin = admin_client.get(reverse('staff:admin-dashboard'))
        assert resp_admin.status_code == 200
        assert resp_admin.wsgi_request.user.email == 'admin@nexisure.test'

        # 3. Verify Tab 2 STILL remains Staff
        resp_staff_after = staff_client.get(reverse('staff:underwriter-dashboard'))
        assert resp_staff_after.status_code == 200
        assert resp_staff_after.wsgi_request.user.email == 'underwriter@nexisure.test'
        assert resp_staff_after.wsgi_request.user.role == UserRole.UNDERWRITER

    def test_requirement_c_admin_remains_admin_after_customer_login(self):
        """
        Requirement C: Admin remains Admin after Customer logs in.
        Tab 3 (admin.localhost:8000) logged in as Admin.
        Tab 1 (customer.localhost:8000) logged in as Customer.
        Tab 3 still retains Admin session and identity.
        """
        admin_client = Client(HTTP_HOST='admin.localhost:8000')
        customer_client = Client(HTTP_HOST='customer.localhost:8000')

        # 1. Admin logs in on admin.localhost
        admin_client.post(reverse('accounts:login'), {
            'email': 'admin@nexisure.test',
            'password': 'DemoAdmin@2026',
        })
        resp_admin1 = admin_client.get(reverse('staff:admin-dashboard'))
        assert resp_admin1.status_code == 200
        assert resp_admin1.wsgi_request.user.email == 'admin@nexisure.test'

        # 2. Customer logs in on customer.localhost
        customer_client.post(reverse('accounts:login'), {
            'email': 'customer@nexisure.test',
            'password': 'DemoCust@2026',
        })
        resp_cust = customer_client.get(reverse('customers:dashboard'))
        assert resp_cust.status_code == 200
        assert resp_cust.wsgi_request.user.email == 'customer@nexisure.test'

        # 3. Verify Tab 3 STILL remains Admin
        resp_admin_after = admin_client.get(reverse('staff:admin-dashboard'))
        assert resp_admin_after.status_code == 200
        assert resp_admin_after.wsgi_request.user.email == 'admin@nexisure.test'
        assert resp_admin_after.wsgi_request.user.role == UserRole.ADMINISTRATOR

    def test_requirement_d_refreshing_any_tab_preserves_its_own_identity(self):
        """
        Requirement D: Refreshing any tab preserves its own identity.
        Simultaneous tabs: Customer, Staff, Admin.
        Repeated GET requests (page reloads) on each tab preserve exact respective identities.
        """
        customer_client = Client(HTTP_HOST='customer.localhost:8000')
        staff_client = Client(HTTP_HOST='staff.localhost:8000')
        admin_client = Client(HTTP_HOST='admin.localhost:8000')

        customer_client.post(reverse('accounts:login'), {'email': 'customer@nexisure.test', 'password': 'DemoCust@2026'})
        staff_client.post(reverse('accounts:login'), {'email': 'underwriter@nexisure.test', 'password': 'DemoStaff@2026'})
        admin_client.post(reverse('accounts:login'), {'email': 'admin@nexisure.test', 'password': 'DemoAdmin@2026'})

        # Simulate multiple refreshes on Tab 1
        for _ in range(3):
            r = customer_client.get(reverse('customers:dashboard'))
            assert r.status_code == 200
            assert r.wsgi_request.user.email == 'customer@nexisure.test'

        # Simulate multiple refreshes on Tab 2
        for _ in range(3):
            r = staff_client.get(reverse('staff:underwriter-dashboard'))
            assert r.status_code == 200
            assert r.wsgi_request.user.email == 'underwriter@nexisure.test'

        # Simulate multiple refreshes on Tab 3
        for _ in range(3):
            r = admin_client.get(reverse('staff:admin-dashboard'))
            assert r.status_code == 200
            assert r.wsgi_request.user.email == 'admin@nexisure.test'

    def test_requirement_e_navigating_between_pages_preserves_its_own_identity(self):
        """
        Requirement E: Navigating between pages preserves its own identity.
        Customer navigates customer portal pages.
        Staff navigates staff portal pages.
        Admin navigates admin pages.
        """
        customer_client = Client(HTTP_HOST='customer.localhost:8000')
        staff_client = Client(HTTP_HOST='staff.localhost:8000')
        admin_client = Client(HTTP_HOST='admin.localhost:8000')

        customer_client.post(reverse('accounts:login'), {'email': 'customer@nexisure.test', 'password': 'DemoCust@2026'})
        staff_client.post(reverse('accounts:login'), {'email': 'underwriter@nexisure.test', 'password': 'DemoStaff@2026'})
        admin_client.post(reverse('accounts:login'), {'email': 'admin@nexisure.test', 'password': 'DemoAdmin@2026'})

        # Customer navigates
        r1 = customer_client.get(reverse('customers:dashboard'))
        assert r1.status_code == 200
        assert r1.wsgi_request.user.email == 'customer@nexisure.test'

        r2 = customer_client.get(reverse('accounts:profile'))
        assert r2.status_code == 200
        assert r2.wsgi_request.user.email == 'customer@nexisure.test'

        r3 = customer_client.get(reverse('vehicles:list'))
        assert r3.status_code == 200
        assert r3.wsgi_request.user.email == 'customer@nexisure.test'

        # Staff navigates
        s1 = staff_client.get(reverse('staff:underwriter-dashboard'))
        assert s1.status_code == 200
        assert s1.wsgi_request.user.email == 'underwriter@nexisure.test'

        s2 = staff_client.get(reverse('staff:my-customers'))
        assert s2.status_code == 200
        assert s2.wsgi_request.user.email == 'underwriter@nexisure.test'

        # Admin navigates
        a1 = admin_client.get(reverse('staff:admin-dashboard'))
        assert a1.status_code == 200
        assert a1.wsgi_request.user.email == 'admin@nexisure.test'

        a2 = admin_client.get(reverse('staff:staff-list'))
        assert a2.status_code == 200
        assert a2.wsgi_request.user.email == 'admin@nexisure.test'

        a3 = admin_client.get('/django-admin/')
        assert a3.status_code == 200
        assert a3.wsgi_request.user.email == 'admin@nexisure.test'

    def test_requirement_f_logging_out_of_one_tab_does_not_log_out_other_tabs(self):
        """
        Requirement F: Logging out of one tab does NOT log out the other tabs.
        Customer logs out from customer.localhost:8000.
        Staff on staff.localhost:8000 and Admin on admin.localhost:8000 remain logged in.
        """
        customer_client = Client(HTTP_HOST='customer.localhost:8000')
        staff_client = Client(HTTP_HOST='staff.localhost:8000')
        admin_client = Client(HTTP_HOST='admin.localhost:8000')

        customer_client.post(reverse('accounts:login'), {'email': 'customer@nexisure.test', 'password': 'DemoCust@2026'})
        staff_client.post(reverse('accounts:login'), {'email': 'underwriter@nexisure.test', 'password': 'DemoStaff@2026'})
        admin_client.post(reverse('accounts:login'), {'email': 'admin@nexisure.test', 'password': 'DemoAdmin@2026'})

        # Tab 1 logs out
        logout_resp = customer_client.post(reverse('accounts:logout'))
        assert logout_resp.status_code in (302, 200)

        # Tab 1 is now logged out
        r_cust = customer_client.get(reverse('customers:dashboard'))
        assert r_cust.status_code == 302  # redirected to login

        # Tab 2 remains fully logged in
        r_staff = staff_client.get(reverse('staff:underwriter-dashboard'))
        assert r_staff.status_code == 200
        assert r_staff.wsgi_request.user.is_authenticated
        assert r_staff.wsgi_request.user.email == 'underwriter@nexisure.test'

        # Tab 3 remains fully logged in
        r_admin = admin_client.get(reverse('staff:admin-dashboard'))
        assert r_admin.status_code == 200
        assert r_admin.wsgi_request.user.is_authenticated
        assert r_admin.wsgi_request.user.email == 'admin@nexisure.test'

    def test_requirement_g_customer_cannot_access_staff_or_admin_pages(self):
        """
        Requirement G: Customer cannot access Staff/Admin pages.
        Customer session gets 403 Forbidden or redirect when attempting to access staff/admin views.
        """
        customer_client = Client(HTTP_HOST='customer.localhost:8000')
        customer_client.post(reverse('accounts:login'), {'email': 'customer@nexisure.test', 'password': 'DemoCust@2026'})

        # Underwriter dashboard
        resp1 = customer_client.get(reverse('staff:underwriter-dashboard'))
        assert resp1.status_code in (403, 302)

        # Claims handler dashboard
        resp2 = customer_client.get(reverse('staff:claims-handler-dashboard'))
        assert resp2.status_code in (403, 302)

        # Admin dashboard
        resp3 = customer_client.get(reverse('staff:admin-dashboard'))
        assert resp3.status_code in (403, 302)

        # Django Admin back-office
        resp4 = customer_client.get('/django-admin/')
        # Non-staff users get redirected to admin login or 403
        assert resp4.status_code in (302, 403)

    def test_requirement_h_staff_cannot_access_admin_only_pages(self):
        """
        Requirement H: Staff cannot access Admin-only pages.
        Staff session gets 403 Forbidden when attempting to access admin dashboard/assignments.
        """
        staff_client = Client(HTTP_HOST='staff.localhost:8000')
        staff_client.post(reverse('accounts:login'), {'email': 'underwriter@nexisure.test', 'password': 'DemoStaff@2026'})

        # Underwriter attempting to access Admin Dashboard
        resp_admin_dash = staff_client.get(reverse('staff:admin-dashboard'))
        assert resp_admin_dash.status_code in (403, 302)

        # Underwriter attempting to access Admin-only Staff Management
        resp_admin_mgmt = staff_client.get(reverse('staff:staff-list'))
        assert resp_admin_mgmt.status_code in (403, 302)

    def test_requirement_i_admin_permissions_remain_intact(self):
        """
        Requirement I: Admin permissions remain intact.
        Admin can access Admin Dashboard, Staff Management, and Django Admin.
        """
        admin_client = Client(HTTP_HOST='admin.localhost:8000')
        admin_client.post(reverse('accounts:login'), {'email': 'admin@nexisure.test', 'password': 'DemoAdmin@2026'})

        # Admin Dashboard
        r1 = admin_client.get(reverse('staff:admin-dashboard'))
        assert r1.status_code == 200

        # Admin Staff Management
        r2 = admin_client.get(reverse('staff:staff-list'))
        assert r2.status_code == 200

        # Django Admin
        r3 = admin_client.get('/django-admin/')
        assert r3.status_code == 200
        assert b"Site administration" in r3.content or b"Administration" in r3.content

    def test_requirement_j_csrf_protection_and_otp_work_on_subdomains(self):
        """
        Requirement J: CSRF protection still works and OTP authentication still works.
        1. Untrusted origin CSRF request is rejected.
        2. Trusted origin CSRF request is allowed.
        3. OTP request & verify endpoints work across subdomains.
        """
        # 1. CSRF Protection: Untrusted Origin rejection
        client_untrusted = Client(
            HTTP_HOST='customer.localhost:8000',
            HTTP_ORIGIN='http://untrusted-attacker.com',
            enforce_csrf_checks=True,
        )
        resp_csrf_fail = client_untrusted.post(
            reverse('accounts:login'),
            {'email': 'customer@nexisure.test', 'password': 'DemoCust@2026'},
        )
        assert resp_csrf_fail.status_code == 403

        # 2. CSRF Protection: Trusted Origin with valid token works
        client_trusted = Client(
            HTTP_HOST='customer.localhost:8000',
            HTTP_ORIGIN='http://customer.localhost:8000',
            enforce_csrf_checks=True,
        )
        # Fetch initial page to obtain CSRF cookie
        get_res = client_trusted.get(reverse('accounts:login'))
        csrf_token = client_trusted.cookies['csrftoken'].value
        resp_csrf_success = client_trusted.post(
            reverse('accounts:login'),
            {
                'email': 'customer@nexisure.test',
                'password': 'DemoCust@2026',
                'csrfmiddlewaretoken': csrf_token,
            },
            HTTP_REFERER='http://customer.localhost:8000/auth/login/',
        )
        assert resp_csrf_success.status_code in (200, 302)

        # 3. OTP Request endpoint functions on subdomain
        otp_client = Client(HTTP_HOST='customer.localhost:8000')
        otp_req_resp = otp_client.post(
            reverse('accounts:otp-request'),
            {'email': 'customer@nexisure.test'},
        )
        assert otp_req_resp.status_code in (200, 302)

        # 4. OTP Verification endpoint functions on subdomain (invalid OTP rejected gracefully)
        otp_verify_resp = otp_client.post(
            reverse('accounts:verify-otp'),
            {'email': 'customer@nexisure.test', 'otp_code': '000000'},
        )
        assert otp_verify_resp.status_code in (200, 302)
