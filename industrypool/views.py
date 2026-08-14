from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from allianceauth.eveonline.models import EveCorporationInfo

from .forms import JobRequestForm
from .models import JobRequest, JobRequestStatus


def _user_corporations(user):
    """Corporations of all of a user's characters, used to scope what they can see/manage."""
    corp_ids = user.character_ownerships.values_list(
        "character__corporation_id", flat=True
    ).distinct()
    return EveCorporationInfo.objects.filter(corporation_id__in=corp_ids)


@login_required
@permission_required("industrypool.basic_access")
def pool_list(request):
    jobs = (
        JobRequest.objects.filter(status=JobRequestStatus.OPEN)
        .select_related("blueprint_type", "corporation", "created_by")
        .order_by("priority", "created_at")
    )
    if not request.user.has_perm("industrypool.view_all_jobs"):
        jobs = jobs.filter(corporation__in=_user_corporations(request.user))
    context = {"jobs": jobs}
    return render(request, "industrypool/pool_list.html", context)


@login_required
@permission_required("industrypool.basic_access")
def my_jobs(request):
    jobs = (
        JobRequest.objects.filter(
            claimed_by=request.user
        )
        | JobRequest.objects.filter(assigned_to=request.user)
    )
    jobs = jobs.select_related("blueprint_type", "corporation", "tracked_job").distinct().order_by("-updated_at")
    return render(request, "industrypool/pool_list.html", {"jobs": jobs, "my_jobs": True})


@login_required
@permission_required("industrypool.manage_pool")
def job_create(request):
    corporations = _user_corporations(request.user)
    if request.method == "POST":
        form = JobRequestForm(request.POST, corporations=corporations)
        if form.is_valid():
            job = form.save(commit=False)
            job.created_by = request.user
            if job.assigned_to_id:
                job.status = JobRequestStatus.ASSIGNED
            job.save()
            messages.success(request, "Job request created.")
            return redirect("industrypool:job_detail", pk=job.pk)
    else:
        form = JobRequestForm(corporations=corporations)
    return render(request, "industrypool/job_form.html", {"form": form})


@login_required
@permission_required("industrypool.basic_access")
def job_detail(request, pk):
    job = get_object_or_404(
        JobRequest.objects.select_related("blueprint_type", "corporation", "tracked_job"), pk=pk
    )
    if not request.user.has_perm("industrypool.view_all_jobs") and job.corporation not in _user_corporations(
        request.user
    ):
        raise PermissionDenied
    return render(request, "industrypool/job_detail.html", {"job": job})


@login_required
@permission_required("industrypool.claim_jobs")
def job_claim(request, pk):
    job = get_object_or_404(JobRequest, pk=pk)
    if not job.is_open:
        messages.error(request, "This job is no longer open.")
    else:
        job.claim(request.user)
        messages.success(request, f"You claimed {job}.")
    return redirect("industrypool:job_detail", pk=job.pk)


@login_required
@permission_required("industrypool.manage_pool")
def job_cancel(request, pk):
    job = get_object_or_404(JobRequest, pk=pk)
    job.cancel()
    messages.success(request, f"Cancelled {job}.")
    return redirect("industrypool:pool_list")
