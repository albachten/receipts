import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import FailedLogin, User


class ImmediateThread:
    """Stand-in for threading.Thread that runs the target right away."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
@mock.patch('core.forms.threading.Thread', ImmediateThread)
class AuthFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('Sally', 'sally@example.com', 'old-pass-123!')
        User.objects.create_user('ray', 'ray@example.com', 'ray-pass-123!')

    # ─── Login ────────────────────────────────────────────────────────────────

    def login(self, identifier, password):
        return self.client.post(reverse('login'), {'username': identifier, 'password': password})

    def test_login_with_username_case_insensitive(self):
        self.assertRedirects(self.login('sally', 'old-pass-123!'), reverse('dashboard'))

    def test_login_with_email_case_insensitive(self):
        self.assertRedirects(self.login('SALLY@example.com', 'old-pass-123!'), reverse('dashboard'))

    def test_email_must_be_unique_ignoring_case(self):
        with self.assertRaises(IntegrityError):
            User.objects.create_user('sally2', 'SALLY@example.com', 'other-pass-123!')

    def test_manage_users_rejects_duplicate_email(self):
        admin = User.objects.create_user('boss', 'boss@example.com', 'boss-pass-123!', is_admin=True)
        self.client.force_login(admin)
        response = self.client.post(reverse('manage_users'), {
            'action': 'create', 'username': 'sally2', 'email': 'Sally@Example.com', 'password': 'x-pass-123!',
        })
        self.assertContains(response, 'already used by another user')
        self.assertFalse(User.objects.filter(username='sally2').exists())

    def test_edit_user_updates_fields(self):
        admin = User.objects.create_user('boss', 'boss@example.com', 'boss-pass-123!', is_admin=True)
        self.client.force_login(admin)
        response = self.client.post(reverse('edit_user', args=[self.user.pk]), {
            'action': 'update', 'account_name': 'sally_r', 'contact': 'sally.r@example.com', 'is_admin': 'on',
        })
        self.assertRedirects(response, reverse('manage_users'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'sally_r')
        self.assertEqual(self.user.email, 'sally.r@example.com')
        self.assertTrue(self.user.is_admin)
        self.assertTrue(self.user.check_password('old-pass-123!'))

    def test_edit_user_sets_password(self):
        admin = User.objects.create_user('boss', 'boss@example.com', 'boss-pass-123!', is_admin=True)
        self.client.force_login(admin)
        response = self.client.post(reverse('edit_user', args=[self.user.pk]), {
            'action': 'set_password', 'new_password': 'new-pass-123!',
        })
        self.assertRedirects(response, reverse('manage_users'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('new-pass-123!'))

    def test_edit_user_rejects_taken_username_and_email(self):
        admin = User.objects.create_user('boss', 'boss@example.com', 'boss-pass-123!', is_admin=True)
        self.client.force_login(admin)
        url = reverse('edit_user', args=[self.user.pk])
        response = self.client.post(url, {'action': 'update', 'account_name': 'RAY', 'contact': 'sally@example.com'})
        self.assertContains(response, 'already taken')
        response = self.client.post(url, {'action': 'update', 'account_name': 'Sally', 'contact': 'Ray@example.com'})
        self.assertContains(response, 'already used by another user')
        self.user.refresh_from_db()
        self.assertEqual((self.user.username, self.user.email), ('Sally', 'sally@example.com'))

    def test_edit_user_requires_admin(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('edit_user', args=[self.user.pk]))
        self.assertEqual(response.status_code, 403)

    def test_profile_rejects_another_users_email(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('profile'), {'action': 'change_email', 'email': 'RAY@example.com'})
        self.assertContains(response, 'already used by another user')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'sally@example.com')

    def test_login_failures_share_one_message(self):
        for identifier, password in [('sally', 'wrong'), ('nobody', 'wrong'), ('no@example.com', 'wrong')]:
            response = self.login(identifier, password)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Invalid username/email or password.')

    # ─── Login lockout ────────────────────────────────────────────────────────

    def test_lockout_after_repeated_failures_blocks_even_correct_password(self):
        for _ in range(5):
            self.login('sally', 'wrong')
        response = self.login('sally', 'old-pass-123!')
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Too many failed sign-in attempts', status_code=429)

    def test_lockout_is_per_ip_using_x_real_ip(self):
        for _ in range(5):
            self.client.post(reverse('login'), {'username': 'sally', 'password': 'wrong'},
                             HTTP_X_REAL_IP='203.0.113.9')
        other = self.client.post(reverse('login'), {'username': 'sally', 'password': 'old-pass-123!'},
                                 HTTP_X_REAL_IP='198.51.100.7')
        self.assertRedirects(other, reverse('dashboard'))

    def test_lockout_expires(self):
        for _ in range(5):
            self.login('sally', 'wrong')
        FailedLogin.objects.update(created_at=timezone.now() - timedelta(minutes=16))
        self.assertRedirects(self.login('sally', 'old-pass-123!'), reverse('dashboard'))

    def test_successful_login_clears_failures(self):
        for _ in range(4):
            self.login('sally', 'wrong')
        self.login('sally', 'old-pass-123!')
        self.assertFalse(FailedLogin.objects.exists())

    # ─── Password rules ───────────────────────────────────────────────────────

    def test_simple_passwords_allowed_if_long_enough(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('profile'), {
            'action': 'change_password', 'current_password': 'old-pass-123!',
            'new_password': 'abc', 'confirm_password': 'abc',
        })
        self.assertContains(response, 'too short')
        response = self.client.post(reverse('profile'), {
            'action': 'change_password', 'current_password': 'old-pass-123!',
            'new_password': '1234', 'confirm_password': '1234',
        })
        self.assertContains(response, 'Password updated.')

    # ─── Forgot username ──────────────────────────────────────────────────────

    def test_forgot_username_sends_username(self):
        response = self.client.post(reverse('forgot_username'), {'email': 'Sally@Example.com'})
        self.assertContains(response, 'If that email address belongs to an account')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['sally@example.com'])
        self.assertIn('Your username is: Sally', mail.outbox[0].body)

    def test_forgot_username_unknown_email_looks_the_same(self):
        known = self.client.post(reverse('forgot_username'), {'email': 'sally@example.com'})
        unknown = self.client.post(reverse('forgot_username'), {'email': 'nobody@example.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(known.content, unknown.content)

    # ─── Forgot password ──────────────────────────────────────────────────────

    def test_password_reset_by_username_or_email(self):
        for identifier in ['SALLY', 'sally@EXAMPLE.com']:
            mail.outbox.clear()
            response = self.client.post(reverse('password_reset'), {'email': identifier})
            self.assertRedirects(response, reverse('password_reset_done'))
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, ['sally@example.com'])

    def test_password_reset_unknown_redirects_without_email(self):
        response = self.client.post(reverse('password_reset'), {'email': 'nobody'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_skips_inactive_users(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(reverse('password_reset'), {'email': 'sally'})
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_link_sets_new_password(self):
        self.client.post(reverse('password_reset'), {'email': 'sally'})
        link = re.search(r'https?://[^/]+(/\S+)', mail.outbox[0].body).group(1)
        # The confirm view swaps the token into the session and redirects.
        response = self.client.get(link, follow=True)
        self.assertContains(response, 'Choose a new password')
        response = self.client.post(response.redirect_chain[-1][0], {
            'new_password1': 'sally',
            'new_password2': 'sally',
        })
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('sally'))
        # The link is single-use.
        self.assertContains(self.client.get(link, follow=True), 'invalid or has already been used')
