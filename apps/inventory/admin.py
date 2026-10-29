from django.contrib import admin

from .models import Unit, UnitEvent


class UnitEventInline(admin.TabularInline):
    model = UnitEvent
    extra = 0
    readonly_fields = ['kind', 'condition', 'booking', 'author', 'comment', 'created_at']


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['inventory_number', 'equipment', 'condition', 'status']
    list_filter = ['status', 'condition', 'equipment__category']
    search_fields = ['inventory_number', 'equipment__name']
    inlines = [UnitEventInline]
