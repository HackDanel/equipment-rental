from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.permissions import admin_required, staff_required
from apps.catalog.models import Equipment

from . import services
from .forms import AddUnitsForm, CommentForm, ConditionForm, FromRepairForm, UnitFilterForm, WriteOffForm
from .models import Unit


@staff_required
def summary(request):
    """Сводка склада по позициям: сколько экземпляров в каком статусе."""
    rows = (Equipment.objects.select_related('category')
            .annotate(**{s: Count('units', filter=Q(units__status=s)) for s in Unit.Status.values})
            .annotate(damaged=Count('units', filter=Q(units__condition='damaged') & ~Q(units__status='written_off')))
            .order_by('category__name', 'name'))
    return render(request, 'inventory/summary.html', {'rows': rows, 'add_form': AddUnitsForm()})


@staff_required
def unit_list(request):
    form = UnitFilterForm(request.GET or None)
    qs = Unit.objects.select_related('equipment')
    equipment = None
    if request.GET.get('equipment', '').isdigit():
        equipment = Equipment.objects.filter(pk=request.GET['equipment']).first()
        qs = qs.filter(equipment=equipment) if equipment else qs
    if form.is_valid():
        c = form.cleaned_data
        if c['q']:
            qs = qs.filter(Q(inventory_number__icontains=c['q']) | Q(equipment__name__icontains=c['q']))
        if c['status']:
            qs = qs.filter(status=c['status'])
        if c['condition']:
            qs = qs.filter(condition=c['condition'])
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'inventory/unit_list.html', {'form': form, 'page': page, 'equipment': equipment})


@staff_required
def unit_detail(request, pk):
    unit = get_object_or_404(Unit.objects.select_related('equipment'), pk=pk)
    events = unit.events.select_related('author', 'booking')[:50]
    return render(request, 'inventory/unit_detail.html', {
        'unit': unit, 'events': events,
        'repair_form': CommentForm(), 'from_repair_form': FromRepairForm(),
        'writeoff_form': WriteOffForm(), 'condition_form': ConditionForm(initial={'condition': unit.condition}),
    })


def _run(request, pk, form_class, action, success):
    form = form_class(request.POST)
    if form.is_valid():
        try:
            action(form.cleaned_data)
            messages.success(request, success)
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
    else:
        messages.error(request, ' '.join(m for errs in form.errors.values() for m in errs))
    return redirect('inventory:unit', pk)


@require_POST
@staff_required
def to_repair(request, pk):
    return _run(request, pk, CommentForm, lambda c: services.send_to_repair(pk, request.user, c['comment']),
                'Экземпляр отправлен в ремонт.')


@require_POST
@staff_required
def from_repair(request, pk):
    return _run(request, pk, FromRepairForm,
                lambda c: services.return_from_repair(pk, request.user, c['condition'], c['comment']),
                'Экземпляр вернулся на склад.')


@require_POST
@staff_required
def set_condition(request, pk):
    return _run(request, pk, ConditionForm,
                lambda c: services.set_condition(pk, request.user, c['condition'], c['comment']),
                'Состояние обновлено.')


@require_POST
@admin_required
def write_off(request, pk):
    return _run(request, pk, WriteOffForm, lambda c: services.write_off(pk, request.user, c['comment']),
                'Экземпляр списан.')


@require_POST
@admin_required
def add_units(request, equipment_pk):
    equipment = get_object_or_404(Equipment, pk=equipment_pk)
    form = AddUnitsForm(request.POST)
    if form.is_valid():
        units = services.add_units(equipment, form.cleaned_data['count'], request.user, form.cleaned_data['condition'])
        messages.success(request, f'{equipment}: добавлено {len(units)} шт. '
                                  f'({units[0].inventory_number} … {units[-1].inventory_number}).')
    else:
        messages.error(request, 'Количество — от 1 до 100.')
    nxt = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return redirect(nxt)
    return redirect('inventory:summary')
