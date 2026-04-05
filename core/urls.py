from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('events/<int:pk>/', views.event_detail, name='event_detail'),
    path('events/<int:pk>/add/', views.add_transaction, name='add_transaction'),
    path('events/<int:pk>/transactions/<int:tx_id>/edit/', views.edit_transaction_view, name='edit_transaction'),
    path('events/<int:pk>/transactions/<int:tx_id>/delete/', views.delete_transaction_view, name='delete_transaction'),
    path('admin/events/create/', views.create_event, name='create_event'),
    path('admin/users/', views.manage_users, name='manage_users'),
    path('admin/events/', views.manage_events, name='manage_events'),
]
