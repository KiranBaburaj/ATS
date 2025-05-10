# Add these URL patterns to your existing urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Existing URLs
    path('', views.home, name='home'),
    path('job-descriptions/', views.manage_job_descriptions, name='manage_job_descriptions'),
    path('job-descriptions/delete/<str:jd_id>/', views.delete_job_description, name='delete_job_description'),
    path('job-descriptions/edit/<str:jd_id>/', views.edit_job_description, name='edit_job_description'),
    path('upload-resume/', views.upload_resume, name='upload_resume'),
    path('analysis-result/<str:result_id>/', views.analysis_result, name='analysis_result'),
    path('applicants/', views.view_applicants, name='view_applicants'),  # Add this new URL pattern
    
    # Authentication URLs
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('profile/', views.profile, name='profile'),
]
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)