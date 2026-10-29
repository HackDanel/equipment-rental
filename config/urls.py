from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

urlpatterns = [
    path('', include('apps.catalog.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('', include('apps.bookings.urls')),
    path('stock/', include('apps.inventory.urls')),
    path('panel/', include('apps.dashboard.urls')),
    path('django-admin/', admin.site.urls),
]

# Фото оборудования отдаёт само приложение: на сервере перед ним только Apache-прокси, а объём файлов мал.
urlpatterns += [path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT})]

admin.site.site_header = 'Прокат оборудования — администрирование'
