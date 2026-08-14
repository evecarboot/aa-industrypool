"""Celery tasks to sync ESI corporation industry jobs against Industry Pool job requests."""

from celery import shared_task

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce
from esi.models import Token
from esi.exceptions import HTTPNotModified
from eveuniverse.models import EveType

from .models import (
    BlueprintInventory,
    CorpHangarDivision,
    JobDependency,
    JobRequest,
    JobRequestMaterial,
    JobRequestStatus,
    TrackedCorporation,
    TrackedIndustryJob,
)
from .discord import send_discord_notification
from .providers import esi
from .utils import esi_id_to_activity

logger = get_extension_logger(__name__)

INDUSTRY_JOBS_SCOPES = ["esi-industry.read_corporation_jobs.v1"]
DIVISIONS_SCOPES = ["esi-corporations.read_divisions.v1"]
ASSETS_SCOPES = ["esi-assets.read_corporation_assets.v1"]
BLUEPRINTS_SCOPES = ["esi-corporations.read_blueprints.v1"]
ESI_TASK_PRIORITY = 7

# ESI location flag -> division number mapping for corporation hangars
HANGAR_LOCATION_FLAGS = {
    f"CorpSAG{i}": i for i in range(1, 8)
}


def _build_container_division_map(assets) -> dict[int, int]:
    """Build a map of container item_id -> division number from corp assets.

    Items inside containers have ``location_flag = "Hangar"`` and
    ``location_id`` set to the container's ``item_id``.  We need to find
    which division each container sits in so we can resolve blueprints
    (and other assets) that are nested inside containers.
    """
    # First pass: find all containers and their direct division
    container_to_division: dict[int, int] = {}
    # item_id -> (location_id, location_flag) for nested lookup
    item_locations: dict[int, tuple] = {}

    for asset in assets:
        item_id = getattr(asset, "item_id", None)
        if item_id is None:
            continue
        location_flag = getattr(asset, "location_flag", "")
        location_id = getattr(asset, "location_id", None)
        item_locations[item_id] = (location_id, location_flag)

        # If this item is directly in a corp hangar division, record it
        division = HANGAR_LOCATION_FLAGS.get(location_flag)
        if division is not None:
            container_to_division[item_id] = division

    # Second pass: resolve nested containers (containers inside containers)
    # We iterate until no more changes are made (max depth = number of items)
    for _ in range(len(item_locations)):
        changed = False
        for item_id, (parent_id, flag) in item_locations.items():
            if item_id in container_to_division:
                continue
            # If parent is a container we already know the division of
            if parent_id is not None and parent_id in container_to_division:
                container_to_division[item_id] = container_to_division[parent_id]
                changed = True
        if not changed:
            break

    return container_to_division


def _resolve_division(location_flag, location_id, container_map):
    """Resolve the corp hangar division for an asset or blueprint.

    Returns the division number (1-7) or ``None`` if the item is not in a
    tracked corp hangar (directly or inside a container).
    """
    division = HANGAR_LOCATION_FLAGS.get(location_flag)
    if division is not None:
        return division
    # If the flag is "Hangar", the item is inside a container - look up the container
    if location_flag == "Hangar" and location_id is not None:
        return container_map.get(location_id)
    return None


@shared_task
def sync_all_corporation_industry_jobs():
    """Kick off a sync task for every actively tracked corporation."""
    for config in TrackedCorporation.objects.filter(is_active=True).select_related("corporation"):
        sync_corporation_industry_jobs.apply_async(
            args=[config.corporation.corporation_id],
            priority=ESI_TASK_PRIORITY,
        )


@shared_task
def release_stale_claims():
    """Return jobs whose claim timeout has elapsed without work starting back to the open pool."""
    claimed_jobs = JobRequest.objects.filter(
        status=JobRequestStatus.CLAIMED, claimed_at__isnull=False
    ).select_related("corporation__industrypool_config", "claimed_by", "blueprint_type")

    for job in claimed_jobs:
        if not job.is_claim_expired:
            continue
        claimant = job.claimed_by
        job.release_claim()
        logger.info("Released expired claim on job request %s (was claimed by %s)", job.pk, claimant)
        if claimant:
            notify(
                claimant,
                title="Industry Pool: claim expired",
                message=(
                    f"Your claim on {job} expired before work started, so it has been "
                    "returned to the open pool."
                ),
                level="warning",
            )
            send_discord_notification(
                "Industry Pool: claim expired",
                f"Claim on {job} expired and was returned to the open pool.",
                level="warning",
                admin=True,
            )


@shared_task
def sync_all_corporation_hangar_divisions():
    """Kick off a hangar division name sync task for every actively tracked corporation."""
    for config in TrackedCorporation.objects.filter(is_active=True).select_related("corporation"):
        sync_corporation_hangar_divisions.apply_async(
            args=[config.corporation.corporation_id],
            priority=ESI_TASK_PRIORITY,
        )


@shared_task(bind=True, base=QueueOnce)
def sync_corporation_hangar_divisions(self, corporation_id: int):
    """Pull hangar division names from ESI so admins can pick recognisable names, not just numbers.

    This only ever creates/updates the ``name`` field - it never changes ``is_active``, so admins
    keep control over which divisions are actually offered as material sources on job requests.
    """
    try:
        config = TrackedCorporation.objects.get(
            corporation__corporation_id=corporation_id, is_active=True
        )
    except TrackedCorporation.DoesNotExist:
        logger.warning("No active TrackedCorporation config for corp %s", corporation_id)
        return

    if not config.director_character:
        logger.warning("No director character configured for corp %s", corporation_id)
        return

    token = Token.get_token(config.director_character.character_id, DIVISIONS_SCOPES)
    if not token:
        logger.error("No valid ESI token with divisions scope for director %s", config.director_character)
        return

    divisions = esi.client.Corporation.GetCorporationsCorporationIdDivisions(
        corporation_id=corporation_id, token=token
    ).result()

    for hangar in divisions.hangar or []:
        name = hangar.name or ""
        if not name or hangar.division is None:
            continue
        CorpHangarDivision.objects.update_or_create(
            corporation=config,
            division_number=hangar.division,
            defaults={"name": name},
        )


@shared_task(bind=True, base=QueueOnce)
def sync_corporation_industry_jobs(self, corporation_id: int):
    """Pull the current industry jobs for a corporation from ESI and update tracked jobs/job requests."""
    try:
        config = TrackedCorporation.objects.get(
            corporation__corporation_id=corporation_id, is_active=True
        )
    except TrackedCorporation.DoesNotExist:
        logger.warning("No active TrackedCorporation config for corp %s", corporation_id)
        return

    if not config.director_character:
        logger.warning("No director character configured for corp %s", corporation_id)
        return

    token = Token.get_token(config.director_character.character_id, INDUSTRY_JOBS_SCOPES)
    if not token:
        logger.error("No valid ESI token found for director %s", config.director_character)
        return

    jobs = esi.client.Corporation.GetCorporationsCorporationIdIndustryJobs(
        corporation_id=corporation_id, token=token
    ).results()

    for job in jobs:
        _update_tracked_job(config, job)


def _builder_owns_installer(job_request: JobRequest, installer_id: int) -> bool:
    builder = job_request.builder
    if not builder:
        return False
    return builder.character_ownerships.filter(character__character_id=installer_id).exists()


def _find_matching_job_request(config: TrackedCorporation, job, blueprint_type: EveType) -> JobRequest | None:
    activity = esi_id_to_activity(job.activity_id)
    if activity is None:
        return None

    candidates = (
        JobRequest.objects.filter(
            tracked_job__isnull=True,
            blueprint_type=blueprint_type,
            corporation=config.corporation,
            activity=activity,
            runs=job.runs,
            status__in=[JobRequestStatus.CLAIMED, JobRequestStatus.ASSIGNED],
        )
        .select_related("claimed_by", "assigned_to")
        .order_by("priority", "created_at")
    )

    for job_request in candidates:
        if _builder_owns_installer(job_request, job.installer_id):
            return job_request
    return None


def _update_tracked_job(config: TrackedCorporation, job) -> None:
    blueprint_type, _ = EveType.objects.get_or_create_esi(id=job.blueprint_type_id)
    installer, _ = EveCharacter.objects.get_or_create_esi(character_id=job.installer_id)

    tracked_job, _ = TrackedIndustryJob.objects.update_or_create(
        job_id=job.job_id,
        defaults={
            "installer": installer,
            "corporation": config.corporation,
            "activity_id": job.activity_id,
            "blueprint_type": blueprint_type,
            "runs": job.runs,
            "start_date": job.start_date,
            "end_date": job.end_date,
            "pause_date": job.pause_date,
            "status": job.status,
        },
    )

    matching_request = _find_matching_job_request(config, job, blueprint_type)
    if matching_request:
        was_not_in_progress = matching_request.status != JobRequestStatus.IN_PROGRESS
        matching_request.tracked_job = tracked_job
        matching_request.status = JobRequestStatus.IN_PROGRESS
        matching_request.save(update_fields=["tracked_job", "status", "updated_at"])

        # Notify the builder that their job has started in ESI
        if was_not_in_progress and matching_request.builder:
            notify(
                matching_request.builder,
                title="Industry Pool: job started",
                message=(
                    f"Your job {matching_request} has been detected as in-progress "
                    "in ESI. Progress tracking is now active."
                ),
                level="info",
            )
            send_discord_notification(
                "Industry Pool: job started",
                f"Job {matching_request} is now in-progress in ESI.",
                level="info",
                admin=True,
            )

    if job.status == "delivered":
        completed = JobRequest.objects.filter(
            tracked_job=tracked_job
        ).exclude(status=JobRequestStatus.COMPLETED)
        for req in completed:
            req.status = JobRequestStatus.COMPLETED
            req.save(update_fields=["status", "updated_at"])
            _handle_job_completion(req)


def _handle_job_completion(job_request: JobRequest) -> None:
    """Handle a job that just completed - notify the builder and resolve dependencies."""
    # If this job has a delivery division set, mark as built (awaiting delivery)
    # rather than completed. The delivery verification task will check for the items.
    if job_request.delivery_division_id:
        job_request.mark_built()
        if job_request.builder:
            try:
                notify(
                    job_request.builder,
                    title="Industry Pool: job built, awaiting delivery",
                    message=(
                        f"Your job {job_request} has been detected as completed in ESI. "
                        f"Please deliver the output to {job_request.delivery_division}."
                    ),
                    level="info",
                )
            except Exception:
                pass
        send_discord_notification(
            "Industry Pool: job built, awaiting delivery",
            f"Job {job_request} completed in ESI. "
            f"Deliver to: {job_request.delivery_division}",
            level="info",
            admin=True,
        )
    else:
        # No delivery tracking - mark as completed directly
        if job_request.builder:
            try:
                notify(
                    job_request.builder,
                    title="Industry Pool: job completed",
                    message=f"Your job {job_request} has been delivered. Well done!",
                    level="success",
                )
            except Exception:
                pass
        send_discord_notification(
            "Industry Pool: job completed",
            f"Job {job_request} has been delivered.",
            level="success",
            admin=True,
        )

    # If this was a copy job, check if any parent manufacturing jobs can now proceed
    if job_request.activity == "copying":
        _resolve_copy_dependencies(job_request)


def _resolve_copy_dependencies(copy_job: JobRequest) -> None:
    """When a copy job completes, mark its dependencies satisfied and unblock parent jobs."""
    deps = JobDependency.objects.filter(
        child_job=copy_job, is_satisfied=False
    ).select_related("parent_job")

    for dep in deps:
        dep.is_satisfied = True
        dep.save(update_fields=["is_satisfied"])

        parent = dep.parent_job
        # Check if ALL dependencies for this parent are now satisfied
        unsatisfied = JobDependency.objects.filter(
            parent_job=parent, is_satisfied=False
        ).exists()

        if not unsatisfied and parent.status == JobRequestStatus.WAITING_FOR_COPIES:
            parent.status = JobRequestStatus.OPEN
            parent.save(update_fields=["status", "updated_at"])
            logger.info(
                "Job %s unblocked - all copy dependencies satisfied", parent.pk
            )
            # Notify corp members who can claim
            if parent.builder:
                notify(
                    parent.builder,
                    title="Industry Pool: copies ready",
                    message=(
                        f"Blueprint copies for {parent} are ready. "
                        "The manufacturing job is now open for claiming."
                    ),
                    level="success",
                )
            send_discord_notification(
                "Industry Pool: copies ready",
                f"Blueprint copies for {parent} are ready. The manufacturing job is now open for claiming.",
                level="success",
                admin=True,
            )


@shared_task
def sync_all_corporation_blueprint_assets():
    """Kick off a blueprint asset sync task for every actively tracked corporation."""
    for config in TrackedCorporation.objects.filter(is_active=True).select_related("corporation"):
        sync_corporation_blueprint_assets.apply_async(
            args=[config.corporation.corporation_id],
            priority=ESI_TASK_PRIORITY,
        )


@shared_task(bind=True, base=QueueOnce)
def sync_corporation_blueprint_assets(self, corporation_id: int):
    """Pull corporation assets from ESI and update blueprint inventory.
    
    This task identifies blueprint items in corp hangars and creates/updates
    BlueprintInventory records with their ME/TE levels and copy counts.
    """
    try:
        config = TrackedCorporation.objects.get(
            corporation__corporation_id=corporation_id, is_active=True
        )
    except TrackedCorporation.DoesNotExist:
        logger.warning("No active TrackedCorporation config for corp %s", corporation_id)
        return

    if not config.director_character:
        logger.warning("No director character configured for corp %s", corporation_id)
        return

    token = Token.get_token(config.director_character.character_id, BLUEPRINTS_SCOPES)
    if not token:
        logger.error("No valid ESI token with blueprints scope for director %s", config.director_character)
        return

    try:
        blueprints = esi.client.Corporation.GetCorporationsCorporationIdBlueprints(
            corporation_id=corporation_id, token=token
        ).results()
    except HTTPNotModified:
        logger.info("Blueprints unchanged since last fetch for corp %s (304 Not Modified)", corporation_id)
        return
    except Exception as e:
        logger.exception("Failed to fetch blueprint assets for corp %s: %s", corporation_id, e)
        return

    if not blueprints:
        logger.info("No blueprint assets found for corp %s", corporation_id)
        return

    # Fetch corp assets to build a container->division map for blueprints
    # that are nested inside containers within corp hangars
    container_map = {}
    assets_token = Token.get_token(config.director_character.character_id, ASSETS_SCOPES)
    if assets_token:
        try:
            assets = esi.client.Assets.GetCorporationsCorporationIdAssets(
                corporation_id=corporation_id, token=assets_token
            ).results()
            container_map = _build_container_division_map(assets)
            logger.info("Built container map with %d entries for corp %s",
                        len(container_map), corporation_id)
        except Exception as e:
            logger.warning("Failed to fetch corp assets for container resolution: %s", e)
    else:
        logger.warning("No assets scope token - blueprints in containers will be skipped")

    # Fetch EveType objects for all blueprint type IDs
    blueprint_type_ids = {b.type_id for b in blueprints}
    blueprint_types = {}
    for type_id in blueprint_type_ids:
        try:
            eve_type, _ = EveType.objects.get_or_create_esi(id=type_id)
            blueprint_types[type_id] = eve_type
        except Exception as e:
            logger.warning("Failed to fetch EveType for blueprint %s: %s", type_id, e)

    # Get active hangar divisions for this corporation keyed by division number
    hangar_divisions = {
        div.division_number: div 
        for div in config.hangar_divisions.filter(is_active=True)
    }

    # Process blueprint assets - track each item individually by item_id
    seen_item_ids = set()
    for blueprint in blueprints:
        if blueprint.type_id not in blueprint_types:
            continue

        blueprint_type = blueprint_types[blueprint.type_id]
        location_flag = getattr(blueprint, 'location_flag', '')
        location_id = getattr(blueprint, 'location_id', None)
        division_number = _resolve_division(location_flag, location_id, container_map)

        # Only process if in a tracked hangar division
        if division_number is None or division_number not in hangar_divisions:
            continue

        hangar_division = hangar_divisions[division_number]

        # ESI blueprints endpoint returns item_id for each individual blueprint
        item_id = getattr(blueprint, 'item_id', None)
        if item_id is None:
            continue

        seen_item_ids.add(item_id)

        # ESI blueprints endpoint: runs == -1 means BPO (unlimited), >= 0 means BPC
        raw_runs = getattr(blueprint, 'runs', -1)
        is_original = raw_runs == -1
        material_efficiency = getattr(blueprint, 'material_efficiency', 0) or 0
        time_efficiency = getattr(blueprint, 'time_efficiency', 0) or 0
        # BPOs store quantity as 1; BPCs store remaining runs
        runs = 1 if is_original else max(raw_runs, 0)

        # Update or create inventory record keyed by (corporation, item_id)
        BlueprintInventory.objects.update_or_create(
            corporation=config,
            item_id=item_id,
            defaults={
                'blueprint_type': blueprint_type,
                'location_division': hangar_division,
                'quantity': runs,
                'material_efficiency': material_efficiency,
                'time_efficiency': time_efficiency,
                'is_original': is_original,
            }
        )

    # Remove inventory items that no longer exist in ESI (blueprint was moved/used/deleted)
    if seen_item_ids:
        BlueprintInventory.objects.filter(
            corporation=config
        ).exclude(item_id__in=seen_item_ids).delete()

    logger.info("Synced blueprint inventory for corp %s: %d blueprint items in tracked divisions",
                corporation_id, len(seen_item_ids))


def _location_flag_to_division(location_flag):
    """Map ESI location flag to corp hangar division number."""
    return HANGAR_LOCATION_FLAGS.get(location_flag)


@shared_task
def sync_all_corporation_material_stock():
    """Kick off a material stock sync task for every actively tracked corporation."""
    for config in TrackedCorporation.objects.filter(is_active=True).select_related("corporation"):
        sync_corporation_material_stock.apply_async(
            args=[config.corporation.corporation_id],
            priority=ESI_TASK_PRIORITY,
        )


@shared_task(bind=True, base=QueueOnce)
def sync_corporation_material_stock(self, corporation_id: int):
    """Pull corporation assets from ESI and update material stock levels on open job requests.

    This reads the corp hangar contents (via esi-assets.read_corporation_assets.v1) and
    updates ``JobRequestMaterial.quantity_available`` for every material on every open or
    waiting job request belonging to the corporation.
    """
    try:
        config = TrackedCorporation.objects.get(
            corporation__corporation_id=corporation_id, is_active=True
        )
    except TrackedCorporation.DoesNotExist:
        logger.warning("No active TrackedCorporation config for corp %s", corporation_id)
        return

    if not config.director_character:
        logger.warning("No director character configured for corp %s", corporation_id)
        return

    token = Token.get_token(config.director_character.character_id, ASSETS_SCOPES)
    if not token:
        logger.error("No valid ESI token with assets scope for director %s", config.director_character)
        return

    try:
        assets = esi.client.Assets.GetCorporationsCorporationIdAssets(
            corporation_id=corporation_id, token=token
        ).results()
    except Exception as e:
        logger.exception("Failed to fetch corp assets for corp %s: %s", corporation_id, e)
        return

    if not assets:
        logger.info("No assets found for corp %s", corporation_id)
        return

    # Build a container->division map so we can resolve items inside containers
    container_map = _build_container_division_map(assets)

    # Build a map of division_number -> {type_id: quantity} from corp hangar assets
    division_stock: dict[int, dict[int, int]] = {}
    for asset in assets:
        location_flag = getattr(asset, "location_flag", "")
        location_id = getattr(asset, "location_id", None)
        division_number = _resolve_division(location_flag, location_id, container_map)
        if division_number is None:
            continue
        type_id = getattr(asset, "type_id", None)
        quantity = getattr(asset, "quantity", 1) or 1
        if type_id is None:
            continue
        division_stock.setdefault(division_number, {})
        division_stock[division_number][type_id] = (
            division_stock[division_number].get(type_id, 0) + quantity
        )

    # Get active hangar divisions for this corporation
    hangar_divisions = {
        div.division_number: div
        for div in config.hangar_divisions.filter(is_active=True)
    }

    # Find all open/waiting job requests for this corporation that have hangar divisions set
    open_jobs = (
        JobRequest.objects.filter(
            corporation=config.corporation,
            status__in=[JobRequestStatus.OPEN, JobRequestStatus.WAITING_FOR_COPIES],
        )
        .prefetch_related("hangar_divisions", "materials")
        .distinct()
    )

    updated_count = 0
    for job in open_jobs:
        job_divisions = job.hangar_divisions.all()
        if not job_divisions:
            continue

        # Sum available stock across all hangar divisions selected on this job
        for material in job.materials.all():
            total_available = 0
            material_type_id = material.eve_type_id
            for division in job_divisions:
                stock = division_stock.get(division.division_number, {})
                total_available += stock.get(material_type_id, 0)

            if material.quantity_available != total_available:
                material.quantity_available = total_available
                material.save(update_fields=["quantity_available"])
                updated_count += 1

    logger.info(
        "Synced material stock for corp %s: %d material rows updated",
        corporation_id, updated_count,
    )


# ---------------------------------------------------------------------------
# Delivery verification
# ---------------------------------------------------------------------------


@shared_task
def verify_all_pending_deliveries():
    """Check all jobs marked as 'built' to see if their output has been delivered."""
    built_jobs = JobRequest.objects.filter(
        status=JobRequestStatus.BUILT,
        delivery_division__isnull=False,
    ).select_related("corporation", "blueprint_type", "delivery_division")

    for job in built_jobs:
        try:
            verify_job_delivery(job.pk)
        except Exception:
            logger.exception("Failed to verify delivery for job %s", job.pk)


def verify_job_delivery(job_pk: int) -> bool:
    """Check if the expected output items are in the delivery division.

    Returns True if delivery is verified, False otherwise.
    """
    job = JobRequest.objects.select_related(
        "corporation", "blueprint_type", "delivery_division"
    ).get(pk=job_pk)

    if not job.delivery_division:
        logger.warning("Job %s has no delivery division set, cannot verify", job_pk)
        return False

    expected_type = job.expected_output_type
    if not expected_type:
        logger.warning("Job %s: could not determine expected output type", job_pk)
        return False

    expected_qty = job.expected_output_quantity

    # Get the corp config
    try:
        config = TrackedCorporation.objects.get(corporation=job.corporation)
    except TrackedCorporation.DoesNotExist:
        logger.warning("Job %s: corporation %s not tracked", job_pk, job.corporation)
        return False

    # Fetch corp assets from ESI
    try:
        token = Token.objects.filter(
            character__character_id=config.director_character_id,
            scopes__scope=ASSETS_SCOPES[0],
        ).first()
        if not token:
            logger.warning("Job %s: no valid token for assets scope", job_pk)
            return False

        assets = esi.client.Assets.get_corporations_corporation_id_assets(
            corporation_id=job.corporation.corporation_id,
            token=token.valid_access_token(),
        ).results()

        # Build container map for division resolution
        container_map = _build_container_division_map(assets)

        # Count items of the expected type in the delivery division
        found_quantity = 0
        target_division = job.delivery_division.division_number

        for asset in assets:
            type_id = asset.get("type_id")
            if type_id != expected_type.id:
                continue

            location_flag = asset.get("location_flag", "")
            location_id = asset.get("location_id")

            division = _resolve_division(location_flag, location_id, container_map)
            if division == target_division:
                found_quantity += asset.get("quantity", 1)

        if found_quantity >= expected_qty:
            # Delivery verified!
            job.mark_delivered()
            logger.info(
                "Delivery verified for job %s: found %d %s in division %d",
                job_pk, found_quantity, expected_type.name, target_division,
            )

            # Notify the builder and admin
            if job.builder:
                try:
                    notify(
                        job.builder,
                        "Industry Pool: Delivery Verified",
                        f"Your job {job} has been verified as delivered. Thank you!",
                        level="success",
                    )
                except Exception:
                    pass

            send_discord_notification(
                "Industry Pool: delivery verified",
                f"Job {job} - {found_quantity} {expected_type.name} found in delivery hangar.",
                level="success",
                admin=True,
            )
            return True
        else:
            logger.info(
                "Job %s: found %d/%d %s in division %d",
                job_pk, found_quantity, expected_qty, expected_type.name, target_division,
            )
            return False

    except HTTPNotModified:
        logger.info("Job %s: assets unchanged since last fetch", job_pk)
        return False
    except Exception:
        logger.exception("Failed to verify delivery for job %s", job_pk)
        return False
