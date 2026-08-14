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
            'copy_count_needed': int,
            'has_bpo': bool,
            'has_bpc': bool,
            'bpo_location': division or None,
        }
    """
    available_quantity = 0
    locations = []
    has_bpo = False
    has_bpc = False
    bpo_location = None

    for division in hangar_divisions:
        # Now there can be multiple inventory rows per type/division (one per item_id)
        inventories = BlueprintInventory.objects.filter(
            blueprint_type=blueprint_type,
            location_division=division,
            quantity__gt=0,
        )

        for inventory in inventories:
            if not inventory.is_available_for_manufacturing:
                continue

            if inventory.is_original:
                has_bpo = True
                bpo_location = division
                locations.append({
                    'division': division,
                    'is_original': True,
                    'me': inventory.material_efficiency,
                    'te': inventory.time_efficiency,
                    'item_id': inventory.item_id,
                })
                # Don't break - keep counting BPCs too
            else:
                has_bpc = True
                available_quantity += inventory.quantity
                locations.append({
                    'division': division,
                    'is_original': False,
                    'me': inventory.material_efficiency,
                    'te': inventory.time_efficiency,
                    'runs': inventory.quantity,
                    'item_id': inventory.item_id,
                })

    needs_copying = available_quantity < quantity_needed
    copy_count_needed = max(0, quantity_needed - available_quantity)

    return {
        'available': not needs_copying,
        'available_quantity': available_quantity,
        'locations': locations,
        'needs_copying': needs_copying,
        'copy_count_needed': copy_count_needed,
        'has_bpo': has_bpo,
        'has_bpc': has_bpc,
        'bpo_location': bpo_location,
    }


def create_copy_job(blueprint_type, corporation, quantity, location_division, created_by):
    """Create a copy job for the specified blueprint.
    
    Returns:
        JobRequest: The created copy job
    """
    # Create copy job request
    copy_job = JobRequest.objects.create(
        corporation=corporation.corporation,
        blueprint_type=blueprint_type,
        activity=JobActivity.COPYING,
        runs=quantity,
        quantity=quantity,  # Number of copies to produce
        status=JobRequestStatus.OPEN,
        priority=1,  # Copy jobs get high priority
        created_by=created_by,
        notes=f"Auto-generated copy job for {quantity} copies"
    )
    
    # Add the source hangar division
    copy_job.hangar_divisions.add(location_division)
    
    # Populate materials for the copy job
    populate_job_materials(copy_job)
    
    logger.info("Created copy job %s for blueprint %s", copy_job.pk, blueprint_type)
    return copy_job


def create_smart_job_request(blueprint_type, quantity, activity, runs, hangar_divisions,
                              corporation, priority, assigned_to, notes, created_by,
                              use_bpo_directly=False):
    """Create a job request with automatic copy job generation if needed.

    This is the main entry point for smart job creation. It checks blueprint
    availability and automatically creates copy jobs if insufficient copies exist.

    :param use_bpo_directly: If True and a BPO is available, use it directly for
        manufacturing without creating copy jobs first.

    Returns:
        tuple: (manufacturing_job, copy_jobs, warnings) where copy_jobs is a list
        of created copy jobs and warnings is a list of warning messages.
    """
    warnings = []

    # Only do blueprint checking for manufacturing activities
    if activity not in (JobActivity.MANUFACTURING, JobActivity.REACTION):
        # Non-manufacturing activities (copying, research, invention) - just create the job
        status = JobRequestStatus.OPEN if not assigned_to else JobRequestStatus.ASSIGNED
        job = JobRequest.objects.create(
            corporation=corporation.corporation,
            blueprint_type=blueprint_type,
            activity=activity,
            runs=runs,
            quantity=quantity,
            status=status,
            priority=priority,
            assigned_to=assigned_to,
            created_by=created_by,
            notes=notes
        )
        if hangar_divisions:
            job.hangar_divisions.set(hangar_divisions)
        populate_job_materials(job)
        return job, [], []

    # Check blueprint availability
    availability = check_blueprint_availability(blueprint_type, hangar_divisions, quantity)

    copy_jobs = []

    # Determine if we need copy jobs
    need_copy_jobs = False

    if availability['available'] and availability['has_bpc']:
        # Sufficient BPCs available - job can proceed
        need_copy_jobs = False
    elif availability['has_bpo'] and use_bpo_directly:
        # BPO available and admin chose to use it directly
        need_copy_jobs = False
    elif availability['has_bpo'] and not availability['has_bpc']:
        # Only BPO available, admin didn't choose bypass - need copies
        need_copy_jobs = True
    elif availability['needs_copying'] and availability['has_bpo']:
        # Not enough BPCs but BPO exists - need copies for the shortfall
        need_copy_jobs = True
    elif availability['needs_copying'] and not availability['has_bpo'] and availability['has_bpc']:
        # Not enough BPCs and no BPO - can't create more copies
        warnings.append(
            f"Insufficient blueprint copies ({availability['available_quantity']} available, "
            f"{quantity} needed) and no BPO found to make copies from. "
            "The job will be created but may need manual copy job creation."
        )
        need_copy_jobs = False
    elif not availability['has_bpo'] and not availability['has_bpc']:
        # No blueprint at all in inventory
        warnings.append(
            "This blueprint was not found in the corporation's tracked hangar divisions. "
            "Make sure the blueprint is in a tracked hangar, or the job will need to be "
            "fulfilled manually."
        )
        need_copy_jobs = False

    if need_copy_jobs and availability['bpo_location']:
        # Create copy jobs from the BPO
        logger.info("Insufficient blueprint copies (%d needed, %d available). Creating copy jobs.",
                    quantity, availability['available_quantity'])

        for i in range(availability['copy_count_needed']):
            copy_job = create_copy_job(
                blueprint_type, corporation, 1, availability['bpo_location'], created_by
            )
            copy_jobs.append(copy_job)

    # Determine job status
    if copy_jobs:
        # Manufacturing job will wait for copies
        status = JobRequestStatus.WAITING_FOR_COPIES
    else:
        status = JobRequestStatus.OPEN if not assigned_to else JobRequestStatus.ASSIGNED

    manufacturing_job = JobRequest.objects.create(
        corporation=corporation.corporation,
        blueprint_type=blueprint_type,
        activity=activity,
        runs=runs,
        quantity=quantity,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        created_by=created_by,
        notes=notes
    )

    # Set hangar divisions via M2M after creation
    if hangar_divisions:
        manufacturing_job.hangar_divisions.set(hangar_divisions)

    # Populate materials
    populate_job_materials(manufacturing_job)

    # Create dependencies if copy jobs were created
    for copy_job in copy_jobs:
        JobDependency.objects.create(
            parent_job=manufacturing_job,
            child_job=copy_job,
            dependency_type='copy_to_manufacture',
            required_quantity=1,
            is_satisfied=False
        )

    logger.info("Created smart job request %s with %d copy dependencies",
                manufacturing_job.pk, len(copy_jobs))

    return manufacturing_job, copy_jobs, warnings