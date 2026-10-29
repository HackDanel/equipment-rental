from django.contrib import admin

from .models import Booking, BookingItem, Fine, StatusChange


class ItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0


class FineInline(admin.TabularInline):
    model = Fine
    extra = 0


class HistoryInline(admin.TabularInline):
    model = StatusChange
    extra = 0
    readonly_fields = ['status', 'author', 'comment', 'created_at']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'equipment', 'quantity', 'start_date', 'end_date', 'status', 'price_total']
    list_filter = ['status', 'equipment__category']
    search_fields = ['client__username', 'client__last_name', 'equipment__name']
    date_hierarchy = 'start_date'
    inlines = [ItemInline, FineInline, HistoryInline]
