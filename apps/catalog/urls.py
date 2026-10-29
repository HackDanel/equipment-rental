from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    path('', views.index, name='index'),
    path('equipment/<int:pk>/', views.detail, name='detail'),
    path('api/quote/', views.api_quote, name='api_quote'),
]
