from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.forms import StaffForm
from apps.accounts.models import User
from apps.accounts.permissions import admin_required
from apps.catalog.forms import CategoryForm, DiscountTierForm, EquipmentForm, RentalSettingsForm
from apps.catalog.models import Category, DiscountTier, Equipment, RentalSettings
from apps.inventory.forms import AddUnitsForm
from apps.inventory.models import Unit

from . import stats


@admin_required
def statistics(request):
    data = stats.collect()
    c = data['charts']
    data['table'] = list(zip(c['months'], c['bookings'], c['revenue'], c['fines']))
    return render(request, 'dashboard/stats.html', data)


# --- Каталог ---

@admin_required
def equipment_list(request):
    q = request.GET.get('q', '').strip()[:100]
    qs = (Equipment.objects.select_related('category')
          .annotate(working=Count('units', filter=Q(units__status__in=Unit.WORKING)),
                    bookings_n=Count('bookings', distinct=True))
          .order_by('category__name', 'name'))
    if q:
        qs = qs.filter(name__icontains=q)
    return render(request, 'dashboard/equipment_list.html', {'items': qs, 'q': q})


@admin_required
def equipment_edit(request, pk=None):
    obj = get_object_or_404(Equipment, pk=pk) if pk else None
    form = EquipmentForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        messages.success(request, f'«{item}» сохранено.')
        if obj is None:
            messages.info(request, 'Добавьте экземпляры на склад, иначе позицию нельзя будет забронировать.')
        return redirect('dashboard:equipment_edit', item.pk)
    return render(request, 'dashboard/equipment_form.html', {
        'form': form, 'obj': obj, 'add_form': AddUnitsForm(),
        'units': obj.units.all() if obj else [],
    })


@admin_required
def category_list(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Категория добавлена.')
        return redirect('dashboard:categories')
    items = Category.objects.annotate(n=Count('equipment'))
    return render(request, 'dashboard/categories.html', {'form': form, 'items': items})


@admin_required
def category_edit(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Категория сохранена.')
        return redirect('dashboard:categories')
    return render(request, 'dashboard/simple_form.html', {'form': form, 'title': f'Категория «{obj}»',
                                                           'back': 'dashboard:categories'})


@require_POST
@admin_required
def category_delete(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    try:
        obj.delete()
        messages.success(request, f'Категория «{obj}» удалена.')
    except ProtectedError:
        messages.error(request, 'В категории есть оборудование — сначала перенесите его.')
    return redirect('dashboard:categories')


# --- Тарифы ---

@admin_required
def tariffs(request):
    rules = RentalSettings.load()
    rules_form = RentalSettingsForm(request.POST if 'save_rules' in request.POST else None, instance=rules)
    tier_form = DiscountTierForm(request.POST if 'add_tier' in request.POST else None)
    if request.method == 'POST':
        if 'save_rules' in request.POST and rules_form.is_valid():
            rules_form.save()
            messages.success(request, 'Правила проката сохранены.')
            return redirect('dashboard:tariffs')
        if 'add_tier' in request.POST and tier_form.is_valid():
            tier_form.save()
            messages.success(request, 'Скидка добавлена.')
            return redirect('dashboard:tariffs')
    prices = Equipment.objects.select_related('category').order_by('category__name', 'name')
    return render(request, 'dashboard/tariffs.html', {
        'rules_form': rules_form, 'tier_form': tier_form, 'tiers': DiscountTier.objects.all(), 'prices': prices,
    })


@require_POST
@admin_required
def tier_delete(request, pk):
    get_object_or_404(DiscountTier, pk=pk).delete()
    messages.success(request, 'Скидка удалена. На уже созданные брони это не влияет.')
    return redirect('dashboard:tariffs')


# --- Сотрудники и пользователи ---

STAFF_ROLES = [User.Role.MANAGER, User.Role.ADMIN]


@admin_required
def staff_list(request):
    staff = User.objects.filter(Q(role__in=STAFF_ROLES) | Q(is_superuser=True)).annotate(
        handled=Count('managed_bookings'),
    ).order_by('role', 'last_name')
    return render(request, 'dashboard/staff_list.html', {'staff': staff})


@admin_required
def staff_edit(request, pk=None):
    # Здесь редактируются только сотрудники: иначе через форму можно сменить пароль клиенту.
    obj = get_object_or_404(User, Q(role__in=STAFF_ROLES) | Q(is_superuser=True), pk=pk) if pk else None
    if obj is not None and obj.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    form = StaffForm(request.POST if request.method == 'POST' else None, instance=obj,
                     initial=None if obj else {'role': User.Role.MANAGER})
    if request.method == 'POST' and form.is_valid():
        if obj == request.user and (not form.cleaned_data['is_active']
                                    or form.cleaned_data['role'] != User.Role.ADMIN):
            # Иначе администратор может случайно лишить себя доступа к панели.
            form.add_error(None, 'Нельзя отключить или понизить свою собственную учётную запись.')
        else:
            user = form.save()
            messages.success(request, f'Сотрудник {user} сохранён.')
            return redirect('dashboard:staff')
    return render(request, 'dashboard/simple_form.html', {
        'form': form, 'title': f'Сотрудник {obj}' if obj else 'Новый сотрудник', 'back': 'dashboard:staff',
    })


@admin_required
def users(request):
    q = request.GET.get('q', '').strip()[:100]
    qs = User.objects.filter(role=User.Role.CLIENT, is_superuser=False).annotate(
        n=Count('bookings', distinct=True),
        unpaid=Count('bookings__fines', filter=Q(bookings__fines__is_paid=False)),
    ).order_by('last_name', 'first_name')
    if q:
        qs = qs.filter(Q(last_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
                       | Q(username__icontains=q))
    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    return render(request, 'dashboard/users.html', {'page': page, 'q': q})


@require_POST
@admin_required
def user_toggle(request, pk):
    user = get_object_or_404(User, pk=pk, role=User.Role.CLIENT, is_superuser=False)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(request, f'{user}: {"доступ восстановлен" if user.is_active else "заблокирован"}.')
    return redirect('dashboard:users')


@require_POST
@admin_required
def user_promote(request, pk):
    """Перевести клиента в менеджеры (например, нового сотрудника, который сам зарегистрировался)."""
    user = get_object_or_404(User, pk=pk, role=User.Role.CLIENT, is_superuser=False)
    user.role = User.Role.MANAGER
    user.save(update_fields=['role'])
    messages.success(request, f'{user} теперь менеджер.')
    return redirect('dashboard:staff')
