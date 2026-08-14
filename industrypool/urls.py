from django.urls import path

from . import views

app_name = "industrypool"

urlpatterns = [
    path("", views.pool_list, name="pool_list"),
    path("my-jobs/", views.my_jobs, name="my_jobs"),
    path("create/", views.job_create, name="job_create"),
    path("<int:pk>/", views.job_detail, name="job_detail"),
    path("<int:pk>/claim/", views.job_claim, name="job_claim"),
    path("<int:pk>/cancel/", views.job_cancel, name="job_cancel"),
]
