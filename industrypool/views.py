from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import JobRequestForm
from .materials import populate_job_materials
from .models import JobRequest, JobRequestStatus
from .utils import user_can_claim_job, user_can_manage_job, user_can_view_job, user_corporations


@login_required
@permission_required("industrypool.basic_access")
def pool_list(request):
    jobs = (
        JobRequest.objects.filter(status__in=[JobRequestStatus.OPEN, JobRequestStatus.WAITING_FOR_COPIES])
        .select_related("blueprint_type", "corporation", "created_by", "assigned_to", "claimed_by")
        .prefetch_related("hangar_divisions")
        .order_by("priority", "created_at")
    )
    if not request.user.has_perm("industrypool.view_all_jobs"):
        jobs = jobs.filter(corporation__in=user_corporations(request.user))
    context = {"jobs": jobs}
    return render(request, "industrypool/pool_list.html", context)


@login_required
@permission_required("industrypool.basic_access")
def my_jobs(request):
    jobs = (
        JobRequest.objects.filter(claimed_by=request.user)
        | JobRequest.objects.filter(assigned_to=request.user)
    )
    jobs = jobs.select_related("blueprint_type", "corporation", "tracked_job", "created_by").prefetch_related("hangar_divisions").distinct().order_by("-updated_at")
    return render(request, "industrypool/pool_list.html", {"jobs": jobs, "my_jobs": True})


@login_required
@permission_required("industrypool.manage_pool")
def job_create(request):
    corporations = user_corporations(request.user)
    if request.method == "POST":
        form = JobRequestForm(request.POST, corporations=corporations)
        if form.is_valid():
            # For now, use the original simple creation
            # TODO: Integrate smart job creation with blueprint checking
            job = form.save(commit=False)
            job.created_by = request.user
            if job.assigned_to_id:
                job.status = JobRequestStatus.ASSIGNED
            job.save()
            form.save_m2m()
            populate_job_materials(job)
            messages.success(request, "Job request created.")
            return redirect("industrypool:job_detail", pk=job.pk)
    else:
        form = JobRequestForm(corporations=corporations)
    return render(request, "industrypool/job_form.html", {"form": form})


@login_required
@permission_required("industrypool.basic_access")
def job_detail(request, pk):
    job = get_object_or_404(
        JobRequest.objects.select_related(
            "blueprint_type", "corporation", "tracked_job", "created_by", "assigned_to", "claimed_by"
        ).prefetch_related("hangar_divisions", "materials__eve_type"),
        pk=pk
    )
    if not user_can_view_job(request.user, job):
        raise PermissionDenied
    return render(request, "industrypool/job_detail.html", {"job": job})


@login_required
@permission_required("industrypool.claim_jobs")
@require_POST
def job_claim(request, pk):
    with transaction.atomic():
        job = (
            JobRequest.objects.select_for_update()
            .filter(pk=pk, status=JobRequestStatus.OPEN)
            .select_related("corporation")
            .first()
        )
        if job is None:
            messages.error(request, "This job is no longer open.")
            return redirect("industrypool:pool_list")
        if not user_can_claim_job(request.user, job):
            raise PermissionDenied
        job.claim(request.user)
    messages.success(request, f"You claimed {job}.")
    return redirect("industrypool:job_detail", pk=job.pk)


@login_required
@permission_required("industrypool.manage_pool")
@require_POST
def job_cancel(request, pk):
    job = get_object_or_404(JobRequest, pk=pk)
    if not user_can_manage_job(request.user, job):
        raise PermissionDenied
    job.cancel()
    messages.success(request, f"Cancelled {job}.")
    return redirect("industrypool:pool_list")
