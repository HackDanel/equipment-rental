from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.statistics, name='stats'),
    path('equipment/', views.equipment_list, name='equipment'),
    path('equipment/new/', views.equipment_edit, name='equipment_new'),
    path('equipment/<int:pk>/', views.equipment_edit, name='equipment_edit'),
    path('categories/', views.category_list, name='categories'),
    path('categories/<int:pk>/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('tariffs/', views.tariffs, name='tariffs'),
    path('tariffs/<int:pk>/delete/', views.tier_delete, name='tier_delete'),
    path('staff/', views.staff_list, name='staff'),
    path('staff/new/', views.staff_edit, name='staff_new'),
    path('staff/<int:pk>/', views.staff_edit, name='staff_edit'),
    path('users/', views.users, name='users'),
    path('users/<int:pk>/toggle/', views.user_toggle, name='user_toggle'),
    path('users/<int:pk>/promote/', views.user_promote, name='user_promote'),
]
