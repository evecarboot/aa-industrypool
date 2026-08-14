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
    path("<int:pk>/comment/", views.add_comment, name="add_comment"),
    # Job templates
    path("templates/", views.template_list, name="template_list"),
    path("templates/create/", views.template_create, name="template_create"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
    # Production queue
    path("queue/", views.production_queue, name="production_queue"),
    # Builder statistics
    path("stats/", views.builder_stats, name="builder_stats"),
    # CSV export
    path("export/", views.export_jobs_csv, name="export_jobs_csv"),
    # Blueprint autocomplete
    path("blueprint-search/", views.blueprint_search, name="blueprint_search"),
    # Priority reordering
    path("reorder/", views.reorder_priority, name="reorder_priority"),
]
