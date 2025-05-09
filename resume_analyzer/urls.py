from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.home, name='home'),
    path('upload-resume/', views.upload_resume, name='upload_resume'),
    path('upload-job-description/<str:resume_id>/', views.upload_job_description, name='upload_job_description'),
    path('analysis-result/<str:result_id>/', views.analysis_result, name='analysis_result'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)