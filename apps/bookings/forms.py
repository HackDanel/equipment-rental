from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.inventory.models import Condition, Unit

from . import services


class BookingForm(forms.Form):
    start_date = forms.DateField(label='С', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    end_date = forms.DateField(label='По (включительно)', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    quantity = forms.IntegerField(label='Количество', min_value=1, max_value=50, initial=1)
    comment = forms.CharField(label='Комментарий', required=False, max_length=255,
                              widget=forms.TextInput(attrs={'placeholder': 'Например, удобное время получения'}))

    def __init__(self, *args, equipment, **kwargs):
        self.equipment = equipment
        kwargs.setdefault('initial', {})
        today = timezone.localdate()
        kwargs['initial'].setdefault('start_date', today)
        kwargs['initial'].setdefault('end_date', today)
        super().__init__(*args, **kwargs)
        self.fields['start_date'].widget.attrs['min'] = today.isoformat()
        self.fields['end_date'].widget.attrs['min'] = today.isoformat()

    def clean(self):
        c = super().clean()
        start, end, qty = c.get('start_date'), c.get('end_date'), c.get('quantity')
        if not (start and end):
            return c
        for field, msg in services.validate_period(start, end).items():
            self.add_error(field, msg)
        if qty and not self.errors:
            free = services.available_count(self.equipment, start, end)
            if qty > free:
                self.add_error('quantity', f'На эти даты свободно только {free} шт.' if free
                               else 'На эти даты свободных экземпляров нет.')
        return c


class RejectForm(forms.Form):
    reason = forms.CharField(label='Причина отказа', max_length=255)


class IssueForm(forms.Form):
    units = forms.ModelMultipleChoiceField(label='Экземпляры', queryset=Unit.objects.none(),
                                           widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, booking, **kwargs):
        super().__init__(*args, **kwargs)
        self.booking = booking
        self.fields['units'].queryset = Unit.objects.filter(
            equipment=booking.equipment, status=Unit.Status.IN_STOCK).order_by('inventory_number')
        self.fields['units'].label_from_instance = lambda u: f'{u.inventory_number} — {u.get_condition_display().lower()}'

    def clean_units(self):
        units = self.cleaned_data['units']
        if len(units) != self.booking.quantity:
            raise forms.ValidationError(f'Нужно выбрать ровно {self.booking.quantity} шт.')
        return units


class ReturnForm(forms.Form):
    """Приём: на каждый выданный экземпляр — состояние, утеря, штраф за повреждение, отметка."""

    def __init__(self, *args, booking, **kwargs):
        super().__init__(*args, **kwargs)
        self.booking = booking
        self.items = list(booking.items.select_related('unit'))
        for item in self.items:
            p = f'i{item.pk}_'
            self.fields[p + 'condition'] = forms.ChoiceField(label='Состояние', choices=Condition.choices,
                                                             initial=item.condition_out)
            self.fields[p + 'lost'] = forms.BooleanField(label='Утерян', required=False)
            self.fields[p + 'damage_fee'] = forms.DecimalField(label='Штраф за повреждение, ₽', required=False,
                                                               min_value=0, max_digits=10, decimal_places=2)
            self.fields[p + 'note'] = forms.CharField(label='Отметка', required=False, max_length=200)

    def rows(self):
        for item in self.items:
            p = f'i{item.pk}_'
            yield item, [self[p + n] for n in ('condition', 'lost', 'damage_fee', 'note')]

    def clean(self):
        c = super().clean()
        for item in self.items:
            p = f'i{item.pk}_'
            fee = c.get(p + 'damage_fee') or Decimal('0')
            if fee and c.get(p + 'lost'):
                self.add_error(p + 'damage_fee', 'За утерю штраф начисляется автоматически.')
            elif fee and c.get(p + 'condition') not in (Condition.WORN, Condition.DAMAGED):
                self.add_error(p + 'damage_fee', 'Штраф за повреждение — только при состоянии «изношено» или «повреждено».')
            if fee > item.booking.equipment.replacement_cost:
                self.add_error(p + 'damage_fee', 'Штраф больше стоимости возмещения.')
        return c

    def lines(self):
        c = self.cleaned_data
        return [services.ReturnLine(item=i, condition=c[f'i{i.pk}_condition'], lost=c[f'i{i.pk}_lost'],
                                    damage_fee=c[f'i{i.pk}_damage_fee'] or Decimal('0'), note=c[f'i{i.pk}_note'])
                for i in self.items]
