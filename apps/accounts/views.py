from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, ProfileForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect('accounts:home')
    form = RegisterForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, 'Регистрация прошла успешно. Теперь можно бронировать оборудование.')
        nxt = request.POST.get('next', '')
        if url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
            return redirect(nxt)
        return redirect('catalog:index')
    return render(request, 'accounts/register.html', {'form': form, 'next': request.GET.get('next', '')})


class LoginView(auth_views.LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True


@login_required
def home(request):
    """Точка входа после логина: каждая роль попадает на свою стартовую страницу."""
    user = request.user
    if user.is_admin_role:
        return redirect('dashboard:stats')
    if user.is_manager:
        return redirect('bookings:manager')
    return redirect('bookings:my')


@login_required
def profile(request):
    form = ProfileForm(request.POST if request.method == 'POST' else None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Профиль сохранён.')
        return redirect('accounts:profile')
    return render(request, 'accounts/profile.html', {'form': form})
