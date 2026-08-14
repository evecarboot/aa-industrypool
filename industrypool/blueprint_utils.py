"""Blueprint-related helper functions for Industry Pool."""

from allianceauth.services.hooks import get_extension_logger

from .materials import populate_job_materials
from .models import BlueprintInventory, JobActivity, JobDependency, JobRequest, JobRequestStatus

logger = get_extension_logger(__name__)


def check_blueprint_availability(blueprint_type, hangar_divisions, quantity_needed=1):
    """Check if sufficient blueprint copies are available in the specified hangars.

    Returns:
        dict: {
            'available': bool,
            'available_quantity': int,
            'locations': list of dicts with location info,
            'needs_copying': bool,
            'copy_count_needed': int
        }
    """
    available_quantity = 0
    locations = []

    for division in hangar_divisions:
        inventory = BlueprintInventory.objects.filter(
            blueprint_type=blueprint_type,
            location_division=division,
            quantity__gt=0,
        ).first()
        if inventory is None or not inventory.is_available_for_manufacturing:
            continue

        if inventory.is_original:
            # A BPO can be used an unlimited number of times, so nothing needs copying.
            available_quantity = quantity_needed
            locations.append({
                'division': division,
                'is_original': True,
                'me': inventory.material_efficiency,
                'te': inventory.time_efficiency,
            })
            break

        available_quantity += inventory.quantity
        locations.append({
            'division': division,
            'is_original': False,
            'me': inventory.material_efficiency,
            'te': inventory.time_efficiency,
            'runs': inventory.quantity,
        })

    needs_copying = available_quantity < quantity_needed
    copy_count_needed = max(0, quantity_needed - available_quantity)

    return {
        'available': not needs_copying,
        'available_quantity': available_quantity,
        'locations': locations,
        'needs_copying': needs_copying,
        'copy_count_needed': copy_count_needed,
    }


def create_copy_job(blueprint_type, corporation, quantity, location_division, created_by):
    """Create a single copy job producing ``quantity`` copies of ``blueprint_type``.

    ``corporation`` is the EveCorporationInfo the job belongs to.
    """
    copy_job = JobRequest.objects.create(
        corporation=corporation,
        blueprint_type=blueprint_type,
        activity=JobActivity.COPYING,
        runs=quantity,
        quantity=quantity,
        status=JobRequestStatus.OPEN,
        priority=1,  # Copy jobs gate the manufacturing job, so they go first
        created_by=created_by,
        notes=f"Auto-generated copy job for {quantity} copies",
    )
    copy_job.hangar_divisions.add(location_division)
    populate_job_materials(copy_job)

    logger.info("Created copy job %s for blueprint %s", copy_job.pk, blueprint_type)
    return copy_job


def create_smart_job_request(
    blueprint_type,
    quantity,
    activity,
    runs,
    hangar_divisions,
    corporation,
    priority,
    assigned_to,
    notes,
    created_by,
):
    """Create a job request, generating a copy job first when blueprint copies are short.

    ``corporation`` is the EveCorporationInfo the job belongs to. The manufacturing job only
    waits when a copy job was actually created for it - otherwise it is posted as normal, so
    it can never end up stuck in ``waiting_for_copies`` with nothing to wait for.

    Returns:
        tuple: (job, copy_jobs)
    """
    copy_jobs = []
    availability = {'needs_copying': False, 'available_quantity': 0, 'locations': []}

    if activity == JobActivity.MANUFACTURING and hangar_divisions:
        # A blueprint copy is consumed per run, so runs is what has to be covered.
        availability = check_blueprint_availability(blueprint_type, hangar_divisions, runs)

    if availability['needs_copying']:
        logger.info(
            "Insufficient blueprint runs (%d needed, %d available) for %s. Creating copy job.",
            runs,
            availability['available_quantity'],
            blueprint_type,
        )
        source = _best_copy_source(availability['locations'])
        if source:
            copy_jobs.append(
                create_copy_job(
                    blueprint_type,
                    corporation,
                    availability['copy_count_needed'],
                    source,
                    created_by,
                )
            )
        else:
            logger.warning(
                "No blueprint for %s in the selected hangars - posting the job without a copy job",
                blueprint_type,
            )

    if copy_jobs:
        status = JobRequestStatus.WAITING_FOR_COPIES
    elif assigned_to:
        status = JobRequestStatus.ASSIGNED
    else:
        status = JobRequestStatus.OPEN

    job = JobRequest.objects.create(
        corporation=corporation,
        blueprint_type=blueprint_type,
        activity=activity,
        runs=runs,
        quantity=quantity,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        created_by=created_by,
        notes=notes,
    )
    if hangar_divisions:
        job.hangar_divisions.set(hangar_divisions)

    populate_job_materials(job)

    for copy_job in copy_jobs:
        JobDependency.objects.create(
            parent_job=job,
            child_job=copy_job,
            dependency_type='copy_to_manufacture',
            required_quantity=copy_job.quantity,
        )

    logger.info("Created job request %s with %d copy dependencies", job.pk, len(copy_jobs))

    return job, copy_jobs


def _best_copy_source(locations):
    """Pick the hangar division to copy from, preferring an original."""
    for location in locations:
        if location['is_original']:
            return location['division']
    return locations[0]['division'] if locations else None


def release_jobs_waiting_on(copy_job: JobRequest) -> list[JobRequest]:
    """Mark dependencies on a finished copy job satisfied and release the jobs waiting on them.

    Returns the parent jobs that were moved out of ``waiting_for_copies``.
    """
    dependencies = JobDependency.objects.filter(
        child_job=copy_job, is_satisfied=False
    ).select_related("parent_job__assigned_to")
    released = []
    for dependency in dependencies:
        dependency.is_satisfied = True
        dependency.save(update_fields=["is_satisfied"])

        parent = dependency.parent_job
        if parent.status != JobRequestStatus.WAITING_FOR_COPIES:
            continue
        if parent.dependencies.filter(is_satisfied=False).exists():
            continue

        parent.status = (
            JobRequestStatus.ASSIGNED if parent.assigned_to_id else JobRequestStatus.OPEN
        )
        parent.save(update_fields=["status", "updated_at"])
        released.append(parent)
        logger.info("Copy job %s satisfied; released job request %s", copy_job.pk, parent.pk)
    return released
