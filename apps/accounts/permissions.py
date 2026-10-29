from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Пропускает только пользователей с одной из ролей. Суперпользователь = admin."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.role in roles or ('admin' in roles and user.is_admin_role):
                return view(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator


admin_required = role_required('admin')
staff_required = role_required('manager', 'admin')
client_required = role_required('client')
