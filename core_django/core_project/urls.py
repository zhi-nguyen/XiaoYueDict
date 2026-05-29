from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/assessments/', include('apps.assessments.urls')),
    path('api/v1/notes/', include('apps.notes.urls')),
    path('api/v1/exams/', include('apps.exams.urls')),
    path('api/v1/dictionary/zh/', include('apps.dictionary_zh.urls')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/gamification/', include('apps.gamification.urls')),
    path('api/v1/subscriptions/', include('apps.subscriptions.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
