from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('events/<int:pk>/', views.event_detail, name='event_detail'),
    path('events/<int:pk>/add/', views.add_transaction, name='add_transaction'),
    path('events/<int:pk>/edit/', views.edit_event, name='edit_event'),
    path('events/<int:pk>/delete/', views.delete_event, name='delete_event'),
    path('events/<int:pk>/archive/', views.archive_event, name='archive_event'),
    path('events/<int:pk>/transactions/<int:tx_id>/edit/', views.edit_transaction_view, name='edit_transaction'),
    path('events/<int:pk>/transactions/<int:tx_id>/delete/', views.delete_transaction_view, name='delete_transaction'),
    path('manage/events/create/', views.create_event, name='create_event'),
    path('manage/users/', views.manage_users, name='manage_users'),
    path('manage/events/', views.manage_events, name='manage_events'),
]
