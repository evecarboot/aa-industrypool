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
                # BPOs can manufacture unlimited times
                available_quantity = quantity_needed  # Consider as available
                locations.append({
                    'division': division,
                    'is_original': True,
                    'me': inventory.material_efficiency,
                    'te': inventory.time_efficiency,
                    'item_id': inventory.item_id,
                })
                break  # BPO found, no need to check more
            else:
                # BPCs are limited by runs
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
                              corporation, priority, assigned_to, notes, created_by):
    """Create a job request with automatic copy job generation if needed.
    
    This is the main entry point for smart job creation. It checks blueprint
    availability and automatically creates copy jobs if insufficient copies exist.
    
    Returns:
        tuple: (manufacturing_job, copy_jobs) where copy_jobs is a list of created copy jobs
    """
    # Check blueprint availability
    availability = check_blueprint_availability(blueprint_type, hangar_divisions, quantity)
    
    copy_jobs = []
    
    if availability['needs_copying']:
        # Create copy jobs first
        logger.info("Insufficient blueprint copies (%d needed, %d available). Creating copy jobs.",
                    quantity, availability['available_quantity'])
        
        # Find best location for copying (prefer BPOs)
        best_location = None
        for location in availability['locations']:
            if location['is_original']:
                best_location = location['division']
                break
        
        if not best_location and availability['locations']:
            best_location = availability['locations'][0]['division']
        
        if best_location:
            for i in range(availability['copy_count_needed']):
                copy_job = create_copy_job(
                    blueprint_type, corporation, 1, best_location, created_by
                )
                copy_jobs.append(copy_job)
    
    # Create the main manufacturing/job request
    if availability['needs_copying']:
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
    
    return manufacturing_job, copy_jobs