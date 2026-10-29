from django.test import TestCase
from django.urls import reverse

from apps.accounts.forms import RegisterForm
from apps.accounts.models import User
from apps.accounts.tests.factories import PASSWORD, make_user


def reg_data(**over):
    data = {'username': 'newbie', 'first_name': 'Анна', 'last_name': 'Новикова', 'email': 'anna@test.local',
            'phone': '+79131234567', 'password1': PASSWORD, 'password2': PASSWORD}
    data.update(over)
    return data


class RegistrationTests(TestCase):
    def test_register_creates_client_and_logs_in(self):
        resp = self.client.post(reverse('accounts:register'), reg_data())
        self.assertRedirects(resp, reverse('catalog:index'))
        user = User.objects.get(username='newbie')
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertNotEqual(user.password, PASSWORD)  # хранится только хеш
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_role_cannot_be_injected(self):
        self.client.post(reverse('accounts:register'), reg_data(role='admin'))
        self.assertEqual(User.objects.get(username='newbie').role, User.Role.CLIENT)

    def test_register_redirects_to_safe_next_only(self):
        resp = self.client.post(reverse('accounts:register') , {**reg_data(), 'next': '/equipment/1/'})
        self.assertRedirects(resp, '/equipment/1/', fetch_redirect_response=False)
        self.client.logout()
        resp = self.client.post(reverse('accounts:register'),
                                {**reg_data(username='x2', email='x2@test.local'), 'next': 'https://evil.example/'})
        self.assertRedirects(resp, reverse('catalog:index'))

    def test_form_validation(self):
        make_user('taken')
        cases = {
            'email': reg_data(email='TAKEN@test.local'),
            'phone': reg_data(phone='12-34'),
            'password2': reg_data(password1='12345678', password2='12345678'),
            'first_name': reg_data(first_name=''),
        }
        for field, data in cases.items():
            form = RegisterForm(data)
            self.assertFalse(form.is_valid(), field)
            self.assertIn(field, form.errors, field)

    def test_phone_boundaries(self):
        self.assertTrue(RegisterForm(reg_data(phone='1234567890')).is_valid())        # 10 цифр
        self.assertFalse(RegisterForm(reg_data(phone='123456789')).is_valid())        # 9
        self.assertTrue(RegisterForm(reg_data(phone='+123456789012345')).is_valid())  # 15
        self.assertFalse(RegisterForm(reg_data(phone='1234567890123456')).is_valid())  # 16


class HomeRedirectTests(TestCase):
    def test_each_role_lands_on_its_page(self):
        for role, url in ((User.Role.CLIENT, '/my/'), (User.Role.MANAGER, '/manager/'), (User.Role.ADMIN, '/panel/')):
            user = make_user(f'u_{role}', role=role)
            self.client.force_login(user)
            self.assertRedirects(self.client.get(reverse('accounts:home')), url, fetch_redirect_response=False)

    def test_superuser_is_admin(self):
        user = User.objects.create_superuser('root', 'root@test.local', PASSWORD)
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_admin_role)
