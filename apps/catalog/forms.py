from django import forms
from django.conf import settings

from .models import Category, DiscountTier, Equipment, RentalSettings


class CatalogFilterForm(forms.Form):
    SORTS = [('name', 'по названию'), ('price', 'сначала дешевле'), ('-price', 'сначала дороже'),
             ('new', 'сначала новые')]
    q = forms.CharField(label='Поиск', required=False, max_length=100)
    group = forms.ChoiceField(label='Направление', required=False,
                              choices=[('', 'Все')] + list(Category.Group.choices))
    category = forms.ModelChoiceField(label='Категория', required=False, queryset=Category.objects.all(),
                                      empty_label='Все')
    price_min = forms.DecimalField(label='Цена от', required=False, min_value=0)
    price_max = forms.DecimalField(label='до', required=False, min_value=0)
    date_from = forms.DateField(label='Свободно с', required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    date_to = forms.DateField(label='по', required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    sort = forms.ChoiceField(label='Сортировка', required=False, choices=SORTS)

    def clean(self):
        c = super().clean()
        if c.get('price_min') is not None and c.get('price_max') is not None and c['price_min'] > c['price_max']:
            self.add_error('price_max', 'Верхняя граница цены меньше нижней.')
        if bool(c.get('date_from')) != bool(c.get('date_to')):
            self.add_error('date_to', 'Укажите обе даты.')
        elif c.get('date_from') and c['date_to'] < c['date_from']:
            self.add_error('date_to', 'Дата окончания раньше даты начала.')
        return c


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'group']


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['category', 'name', 'description', 'photo', 'price_per_day', 'deposit', 'replacement_cost',
                  'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size') and photo.size > settings.MAX_PHOTO_SIZE:
            raise forms.ValidationError('Фото больше 5 МБ.')
        return photo


class DiscountTierForm(forms.ModelForm):
    class Meta:
        model = DiscountTier
        fields = ['min_days', 'percent']


class RentalSettingsForm(forms.ModelForm):
    class Meta:
        model = RentalSettings
        fields = ['late_fee_multiplier', 'max_rental_days', 'max_advance_days']
