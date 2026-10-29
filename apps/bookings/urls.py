from django.urls import path

from . import views

app_name = 'bookings'

urlpatterns = [
    path('equipment/<int:equipment_pk>/book/', views.create, name='create'),
    path('my/', views.my_list, name='my'),
    path('bookings/<int:pk>/', views.detail, name='detail'),
    path('bookings/<int:pk>/cancel/', views.cancel, name='cancel'),
    path('manager/', views.manager, name='manager'),
    path('manager/<int:pk>/confirm/', views.confirm, name='confirm'),
    path('manager/<int:pk>/reject/', views.reject, name='reject'),
    path('manager/<int:pk>/issue/', views.issue, name='issue'),
    path('manager/<int:pk>/return/', views.return_view, name='return'),
    path('manager/fines/<int:pk>/paid/', views.fine_paid, name='fine_paid'),
]
