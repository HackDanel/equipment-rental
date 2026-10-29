from django.contrib import admin

from .models import Category, DiscountTier, Equipment, RentalSettings


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'group']
    list_filter = ['group']


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price_per_day', 'deposit', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name']


admin.site.register(DiscountTier)
admin.site.register(RentalSettings)
