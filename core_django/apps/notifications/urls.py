from django.urls import path
from . import views

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='notifications-list'),
    path('unread/', views.UnreadNotificationsView.as_view(), name='notifications-unread'),
    path('mark-read/', views.MarkNotificationsReadView.as_view(), name='notifications-mark-read'),
    path('count/', views.UnreadCountView.as_view(), name='notifications-count'),
]
