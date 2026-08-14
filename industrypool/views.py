"""Views for the Industry Pool app."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from eveuniverse.models import EveType

from allianceauth.eveonline.models import EveCorporationInfo

from .forms import JobRequestForm
from .blueprint_utils import create_smart_job_request
from .discord import send_discord_dm, send_discord_notification
from .models import (
    BlueprintInventory,
    JobComment,
    JobRequest,
    JobRequestStatus,
    JobTemplate,
    TrackedCorporation,
)
from .utils import user_can_claim_job, user_can_manage_job, user_can_view_job, user_corporations


@login_required
@permission_required("industrypool.basic_access")
def pool_list(request):
    """List open/waiting jobs in the pool, optionally filtered by corporation."""
    jobs = (
        JobRequest.objects.filter(status__in=[JobRequestStatus.OPEN, JobRequestStatus.WAITING_FOR_COPIES])
        .select_related("blueprint_type", "corporation", "created_by", "assigned_to", "claimed_by")
        .prefetch_related("hangar_divisions")
        .order_by("priority", "created_at")
    )

    # Multi-corporation filter
    user_corps = user_corporations(request.user)
    if not request.user.has_perm("industrypool.view_all_jobs"):
        jobs = jobs.filter(corporation__in=user_corps)
        available_corps = user_corps
    else:
        available_corps = EveCorporationInfo.objects.filter(
            pk__in=jobs.values_list("corporation_id", flat=True).distinct()
        )

    selected_corp = request.GET.get("corporation")
    if selected_corp:
        jobs = jobs.filter(corporation_id=selected_corp)

    context = {
        "jobs": jobs,
        "available_corps": available_corps,
        "selected_corp": selected_corp,
    }
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
            use_bpo_directly = form.cleaned_data.get("use_bpo_directly", False)
            hangar_divisions = list(form.cleaned_data.get("hangar_divisions", []))

            # Get the TrackedCorporation for this corp
            try:
                tracked_corp = TrackedCorporation.objects.get(
                    corporation=form.cleaned_data["corporation"],
                    is_active=True,
                )
            except TrackedCorporation.DoesNotExist:
                messages.error(request, "This corporation is not tracked. Add it in admin first.")
                return redirect("industrypool:job_create")

            job, copy_jobs, warnings = create_smart_job_request(
                blueprint_type=form.cleaned_data["blueprint_type"],
                quantity=form.cleaned_data["quantity"],
                activity=form.cleaned_data["activity"],
                runs=form.cleaned_data["runs"],
                hangar_divisions=hangar_divisions,
                corporation=tracked_corp,
                priority=form.cleaned_data["priority"],
                assigned_to=form.cleaned_data.get("assigned_to"),
                notes=form.cleaned_data.get("notes", ""),
                created_by=request.user,
                use_bpo_directly=use_bpo_directly,
            )

            # Set delivery division if selected
            delivery_division = form.cleaned_data.get("delivery_division")
            if delivery_division:
                job.delivery_division = delivery_division
                job.save(update_fields=["delivery_division", "updated_at"])

            messages.success(request, "Job request created.")
            for warning in warnings:
                messages.warning(request, warning)
            if copy_jobs:
                messages.info(
                    request,
                    f"Created {len(copy_jobs)} copy job(s). The manufacturing job will "
                    "become available once copies are completed."
                )

            # Discord notifications
            bp_name = job.blueprint_type.name if job.blueprint_type else "Unknown"
            corp_name = job.corporation.corporation_name if job.corporation else "Unknown"
            job_url = request.build_absolute_uri(
                reverse("industrypool:job_detail", kwargs={"pk": job.pk})
            )
            if job.assigned_to:
                # Direct assignment - DM the assigned user
                send_discord_dm(
                    job.assigned_to,
                    "Industry Pool: Job Assigned",
                    f"You have been assigned a job: **{bp_name}** ({job.get_activity_display()})\n"
                    f"Corporation: {corp_name}\n"
                    f"Runs: {job.runs} | Quantity: {job.quantity}\n"
                    f"View: {job_url}",
                    level="info",
                )
            elif job.status == JobRequestStatus.OPEN:
                # Open pool job - post to public webhook
                send_discord_notification(
                    "Industry Pool: New Job Available",
                    f"**{bp_name}** ({job.get_activity_display()})\n"
                    f"Corporation: {corp_name}\n"
                    f"Runs: {job.runs} | Quantity: {job.quantity}\n"
                    f"Priority: {job.priority}\n"
                    f"View: {job_url}",
                    level="info",
                )
            elif job.status == JobRequestStatus.WAITING_FOR_COPIES:
                # Waiting for copies - admin notification only
                send_discord_notification(
                    "Industry Pool: Job waiting for copies",
                    f"**{bp_name}** ({job.get_activity_display()})\n"
                    f"Corporation: {corp_name}\n"
                    f"Created {len(copy_jobs)} copy job(s). Manufacturing job will open once copies are done.\n"
                    f"View: {job_url}",
                    level="info",
                    admin=True,
                )

            return redirect("industrypool:job_detail", pk=job.pk)
    else:
        # Pre-fill from template if requested
        initial = {}
        template_id = request.GET.get("template")
        if template_id:
            try:
                tmpl = JobTemplate.objects.get(pk=template_id)
                initial = {
                    "corporation": tmpl.corporation_id,
                    "blueprint_type": tmpl.blueprint_type_id,
                    "activity": tmpl.activity,
                    "runs": tmpl.runs,
                    "quantity": tmpl.quantity,
                    "priority": tmpl.priority,
                    "notes": tmpl.notes,
                }
            except JobTemplate.DoesNotExist:
                pass
        form = JobRequestForm(corporations=corporations, initial=initial)
    templates = JobTemplate.objects.filter(corporation__in=corporations)
    return render(request, "industrypool/job_form.html", {"form": form, "templates": templates})


@login_required
@permission_required("industrypool.basic_access")
def job_detail(request, pk):
    job = get_object_or_404(
        JobRequest.objects.select_related(
            "blueprint_type", "corporation", "tracked_job", "created_by", "assigned_to", "claimed_by"
        ).prefetch_related("hangar_divisions", "materials__eve_type", "comments__author"),
        pk=pk
    )
    if not user_can_view_job(request.user, job):
        raise PermissionDenied

    # Estimated build time from eveuniverse industry activity data
    estimated_time = _get_estimated_build_time(job)

    context = {
        "job": job,
        "estimated_time": estimated_time,
    }
    return render(request, "industrypool/job_detail.html", context)


def _get_estimated_build_time(job):
    """Try to estimate the build time for a job from eveuniverse SDE data."""
    from .utils import activity_to_esi_id

    activity_id = activity_to_esi_id(job.activity)
    if activity_id is None:
        return None

    try:
        from eveuniverse.models import EveIndustryActivityDuration
        duration = EveIndustryActivityDuration.objects.filter(
            eve_type=job.blueprint_type,
            activity_id=activity_id,
        ).first()
        if duration and duration.time:
            return duration.time * job.runs
    except Exception:
        pass
    return None


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


@login_required
@permission_required("industrypool.basic_access")
@require_POST
def job_mark_built(request, pk):
    """Builder marks a job as built in EVE, awaiting delivery."""
    job = get_object_or_404(JobRequest, pk=pk)
    if not user_can_view_job(request.user, job):
        raise PermissionDenied
    # Only the builder (claimed_by or assigned_to) can mark as built
    if request.user != job.builder:
        raise PermissionDenied
    if job.status not in (JobRequestStatus.IN_PROGRESS, JobRequestStatus.CLAIMED, JobRequestStatus.ASSIGNED):
        messages.error(request, "This job cannot be marked as built in its current state.")
        return redirect("industrypool:job_detail", pk=job.pk)
    job.mark_built()
    messages.success(request, "Job marked as built. Please deliver the items to the specified hangar.")
    return redirect("industrypool:job_detail", pk=job.pk)


@login_required
@permission_required("industrypool.manage_pool")
@require_POST
def verify_delivery(request, pk):
    """Admin manually triggers delivery verification for a job."""
    from .tasks import verify_job_delivery
    job = get_object_or_404(JobRequest, pk=pk)
    if not user_can_manage_job(request.user, job):
        raise PermissionDenied
    if job.status != JobRequestStatus.BUILT:
        messages.error(request, "Can only verify delivery for jobs marked as built.")
        return redirect("industrypool:job_detail", pk=job.pk)
    # Run verification synchronously for immediate feedback
    delivered = verify_job_delivery(job.pk)
    if delivered:
        messages.success(request, "Delivery verified! Items found in the delivery hangar.")
    else:
        messages.warning(request, "Items not yet found in the delivery hangar. Make sure the builder has delivered them.")
    return redirect("industrypool:job_detail", pk=job.pk)


# --- Job Comments ---

@login_required
@permission_required("industrypool.basic_access")
@require_POST
def add_comment(request, pk):
    """Add a comment / progress update to a job request."""
    job = get_object_or_404(JobRequest, pk=pk)
    if not user_can_view_job(request.user, job):
        raise PermissionDenied
    text = request.POST.get("text", "").strip()
    if text:
        JobComment.objects.create(
            job_request=job,
            author=request.user,
            text=text,
        )
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Comment cannot be empty.")
    return redirect("industrypool:job_detail", pk=job.pk)


# --- Job Templates ---

@login_required
@permission_required("industrypool.manage_pool")
def template_list(request):
    corporations = user_corporations(request.user)
    templates = JobTemplate.objects.filter(corporation__in=corporations).select_related(
        "blueprint_type", "corporation", "created_by"
    )
    return render(request, "industrypool/template_list.html", {"templates": templates})


@login_required
@permission_required("industrypool.manage_pool")
@require_POST
def template_create(request):
    """Save an existing job as a template, or create one from POST data."""
    corporations = user_corporations(request.user)
    name = request.POST.get("name", "").strip()
    corporation_id = request.POST.get("corporation")
    blueprint_type_id = request.POST.get("blueprint_type")

    if not name:
        messages.error(request, "Template name is required.")
        return redirect("industrypool:template_list")

    try:
        corp = EveCorporationInfo.objects.get(pk=corporation_id)
        if corp not in corporations:
            raise PermissionDenied
        bp_type = EveType.objects.get(pk=blueprint_type_id)
    except (EveCorporationInfo.DoesNotExist, EveType.DoesNotExist):
        messages.error(request, "Invalid corporation or blueprint type.")
        return redirect("industrypool:template_list")

    template = JobTemplate.objects.create(
        name=name,
        corporation=corp,
        blueprint_type=bp_type,
        activity=request.POST.get("activity", "manufacturing"),
        runs=int(request.POST.get("runs", 1)),
        quantity=int(request.POST.get("quantity", 1)),
        priority=int(request.POST.get("priority", 3)),
        notes=request.POST.get("notes", ""),
        created_by=request.user,
    )
    messages.success(request, f"Template '{template.name}' created.")
    return redirect("industrypool:template_list")


@login_required
@permission_required("industrypool.manage_pool")
@require_POST
def template_delete(request, pk):
    template = get_object_or_404(JobTemplate, pk=pk)
    corporations = user_corporations(request.user)
    if template.corporation not in corporations:
        raise PermissionDenied
    template.delete()
    messages.success(request, "Template deleted.")
    return redirect("industrypool:template_list")


# --- Production Queue ---

@login_required
@permission_required("industrypool.basic_access")
def production_queue(request):
    """Timeline view of all in-progress jobs with ESI end dates."""
    jobs = (
        JobRequest.objects.filter(
            status=JobRequestStatus.IN_PROGRESS,
            tracked_job__isnull=False,
        )
        .select_related("blueprint_type", "corporation", "tracked_job", "claimed_by", "assigned_to")
        .order_by("tracked_job__end_date")
    )
    if not request.user.has_perm("industrypool.view_all_jobs"):
        jobs = jobs.filter(corporation__in=user_corporations(request.user))
    return render(request, "industrypool/production_queue.html", {"jobs": jobs})


# --- Builder Statistics ---

@login_required
@permission_required("industrypool.basic_access")
def builder_stats(request):
    """Leaderboard of builders by completed job count."""
    from collections import Counter
    from django.contrib.auth import get_user_model
    User = get_user_model()

    user_corps = user_corporations(request.user)
    completed = JobRequest.objects.filter(
        status=JobRequestStatus.COMPLETED
    ).select_related("claimed_by", "assigned_to")
    if not request.user.has_perm("industrypool.view_all_jobs"):
        completed = completed.filter(corporation__in=user_corps)

    # Count completed jobs per user (claimed_by takes priority, then assigned_to)
    counts = Counter()
    for job in completed:
        builder = job.claimed_by or job.assigned_to
        if builder:
            counts[builder.pk] += 1

    if not counts:
        return render(request, "industrypool/builder_stats.html", {"builders": []})

    # Fetch user objects and attach completed_count
    builders = list(User.objects.filter(pk__in=counts.keys()))
    for builder in builders:
        builder.completed_count = counts[builder.pk]
    builders.sort(key=lambda b: b.completed_count, reverse=True)

    return render(request, "industrypool/builder_stats.html", {"builders": builders})


# --- CSV Export ---

@login_required
@permission_required("industrypool.manage_pool")
def export_jobs_csv(request):
    """Export all job requests as a CSV file."""
    user_corps = user_corporations(request.user)
    jobs = JobRequest.objects.select_related(
        "blueprint_type", "corporation", "created_by", "assigned_to", "claimed_by"
    ).order_by("-created_at")
    if not request.user.has_perm("industrypool.view_all_jobs"):
        jobs = jobs.filter(corporation__in=user_corps)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="industrypool_jobs.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "ID", "Blueprint", "Activity", "Runs", "Quantity", "Status",
        "Priority", "Corporation", "Assigned To", "Claimed By",
        "Created By", "Created At", "Updated At",
    ])

    for job in jobs:
        writer.writerow([
            job.pk,
            job.blueprint_type.name if job.blueprint_type else "",
            job.get_activity_display(),
            job.runs,
            job.quantity,
            job.get_status_display(),
            job.priority,
            job.corporation.corporation_name if hasattr(job.corporation, 'corporation_name') else str(job.corporation),
            job.assigned_to.username if job.assigned_to else "",
            job.claimed_by.username if job.claimed_by else "",
            job.created_by.username if job.created_by else "",
            job.created_at.strftime("%Y-%m-%d %H:%M"),
            job.updated_at.strftime("%Y-%m-%d %H:%M"),
        ])

    return response


# --- Blueprint Autocomplete ---

@login_required
@permission_required("industrypool.basic_access")
def blueprint_search(request):
    """AJAX endpoint for blueprint type autocomplete.

    Returns JSON: [{"id": 123, "text": "Sabre", "in_inventory": true}, ...]

    Searches ALL buildable types in the SDE (blueprints, reaction formulas, etc.).
    Marks which ones the corp currently has in its inventory.
    """
    query = request.GET.get("q", "").strip()

    # Get all EveType IDs that have industry activity data (i.e. are buildable)
    # These are types that appear as eve_type in EveIndustryActivityDuration
    try:
        from eveuniverse.models import EveIndustryActivityDuration
        buildable_ids = set(
            EveIndustryActivityDuration.objects.values_list("eve_type_id", flat=True).distinct()
        )
    except Exception:
        # Fallback: if eveuniverse tables aren't populated, search inventory only
        buildable_ids = set(
            BlueprintInventory.objects.values_list("blueprint_type_id", flat=True).distinct()
        )

    # Get corp inventory IDs for marking
    try:
        corp_inventory_ids = set(
            BlueprintInventory.objects.values_list("blueprint_type_id", flat=True).distinct()
        )
    except Exception:
        corp_inventory_ids = set()

    if query:
        results = (
            EveType.objects.filter(
                name__icontains=query,
                published=True,
            )
            .order_by("name")[:100]
        )
    else:
        # No query: show all buildable types (limited to a reasonable number)
        results = (
            EveType.objects.filter(
                published=True,
            )
            .order_by("name")[:100]
        )

    # Filter to only buildable types, but if eveuniverse has no data loaded,
    # fall back to returning all matching published types so the user can still
    # find things. The smart job creation will warn if the corp doesn't have it.
    if buildable_ids:
        items = [
            {
                "id": r.id,
                "text": r.name,
                "in_inventory": r.id in corp_inventory_ids,
            }
            for r in results
            if r.id in buildable_ids
        ]
    else:
        items = [
            {
                "id": r.id,
                "text": r.name,
                "in_inventory": r.id in corp_inventory_ids,
            }
            for r in results
        ]

    return JsonResponse(items, safe=False)


# --- Drag-and-Drop Priority Reordering ---

@login_required
@permission_required("industrypool.manage_pool")
@require_POST
def reorder_priority(request):
    """AJAX endpoint to reorder job priorities via drag-and-drop.

    Expects POST data: job_ids=<comma-separated list of job IDs in new order>
    """
    job_ids_str = request.POST.get("job_ids", "")
    if not job_ids_str:
        return JsonResponse({"ok": False, "error": "No job IDs provided"})

    job_ids = [int(jid) for jid in job_ids_str.split(",") if jid.strip()]

    user_corps = user_corporations(request.user)
    with transaction.atomic():
        for index, job_id in enumerate(job_ids, start=1):
            job = JobRequest.objects.filter(pk=job_id).first()
            if job and (request.user.has_perm("industrypool.view_all_jobs") or job.corporation in user_corps):
                job.priority = index
                job.save(update_fields=["priority", "updated_at"])

    return JsonResponse({"ok": True})
