from django import forms

from .models import Condition, Unit

WORKING_CONDITIONS = [c for c in Condition.choices if c[0] != Condition.DAMAGED]


class UnitFilterForm(forms.Form):
    q = forms.CharField(label='Номер или название', required=False, max_length=100)
    status = forms.ChoiceField(label='Статус', required=False, choices=[('', 'Все')] + list(Unit.Status.choices))
    condition = forms.ChoiceField(label='Состояние', required=False, choices=[('', 'Любое')] + list(Condition.choices))


class AddUnitsForm(forms.Form):
    count = forms.IntegerField(label='Сколько экземпляров', min_value=1, max_value=100, initial=1)
    condition = forms.ChoiceField(label='Состояние', choices=WORKING_CONDITIONS, initial=Condition.EXCELLENT)


class CommentForm(forms.Form):
    comment = forms.CharField(label='Комментарий', required=False, max_length=255)


class WriteOffForm(forms.Form):
    comment = forms.CharField(label='Причина списания', max_length=255)


class FromRepairForm(forms.Form):
    condition = forms.ChoiceField(label='Состояние после ремонта', choices=WORKING_CONDITIONS)
    comment = forms.CharField(label='Что сделано', required=False, max_length=255)


class ConditionForm(forms.Form):
    condition = forms.ChoiceField(label='Состояние', choices=Condition.choices)
    comment = forms.CharField(label='Комментарий', required=False, max_length=255)
