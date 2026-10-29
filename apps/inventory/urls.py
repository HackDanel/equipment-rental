from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.summary, name='summary'),
    path('units/', views.unit_list, name='units'),
    path('units/<int:pk>/', views.unit_detail, name='unit'),
    path('units/<int:pk>/repair/', views.to_repair, name='to_repair'),
    path('units/<int:pk>/repaired/', views.from_repair, name='from_repair'),
    path('units/<int:pk>/condition/', views.set_condition, name='condition'),
    path('units/<int:pk>/write-off/', views.write_off, name='write_off'),
    path('equipment/<int:equipment_pk>/add/', views.add_units, name='add_units'),
]
