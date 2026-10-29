def nav(request):
    """Счётчик новых броней в меню менеджера и администратора."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or user.is_client:
        return {}
    from apps.bookings.models import Booking, Status
    return {'nav_new_bookings': Booking.objects.filter(status=Status.NEW).count()}
