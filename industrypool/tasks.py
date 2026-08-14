"""Celery tasks to sync ESI corporation industry jobs against Industry Pool job requests."""

from celery import shared_task

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce
from esi.models import Token
from eveuniverse.models import EveType

from .models import (
    BlueprintInventory,
    CorpHangarDivision,
    JobRequest,
    JobRequestStatus,
    TrackedCorporation,
    TrackedIndustryJob,
)
from .providers import esi
from .utils import esi_id_to_activity

logger = get_extension_logger(__name__)

INDUSTRY_JOBS_SCOPES = ["esi-industry.read_corporation_jobs.v1"]
DIVISIONS_SCOPES = ["esi-corporations.read_divisions.v1"]
ASSETS_SCOPES = ["esi-assets.read_corporation_assets.v1"]
ESI_TASK_PRIORITY = 7


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


@shared_task
def sync_all_corporation_hangar_divisions():
    """Kick off a hangar division name sync task for every actively tracked corporation."""
    for config in TrackedCorporation.objects.filter(is_active=True).select_related("corporation"):
        sync_corporation_hangar_divisions.apply_async(
            args=[config.corporation.corporation_id],
            priority=ESI_TASK_PRIORITY,
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
        matching_request.tracked_job = tracked_job
        matching_request.status = JobRequestStatus.IN_PROGRESS
        matching_request.save(update_fields=["tracked_job", "status", "updated_at"])

    if job.status == "delivered":
        JobRequest.objects.filter(tracked_job=tracked_job).update(status=JobRequestStatus.COMPLETED)


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

    token = Token.get_token(config.director_character.character_id, ASSETS_SCOPES)
    if not token:
        logger.error("No valid ESI token with assets scope for director %s", config.director_character)
        return

    try:
        assets = esi.client.Assets.GetCorporationsCorporationIdAssets(
            corporation_id=corporation_id, token=token
        ).results()
    except Exception as e:
        logger.exception("Failed to fetch assets for corp %s: %s", corporation_id, e)
        return

    # Get blueprint type IDs from assets
    blueprint_type_ids = set()
    for item in assets:
        # Blueprint items in ESI have specific characteristics
        if hasattr(item, 'is_blueprint_copy') or (hasattr(item, 'type_id') and is_blueprint_type_id(item.type_id)):
            blueprint_type_ids.add(item.type_id)
    
    if not blueprint_type_ids:
        logger.info("No blueprint assets found for corp %s", corporation_id)
        return

    # Fetch EveType objects for all blueprints
    blueprint_types = {}
    for type_id in blueprint_type_ids:
        try:
            eve_type, _ = EveType.objects.get_or_create_esi(id=type_id)
            blueprint_types[type_id] = eve_type
        except Exception as e:
            logger.warning("Failed to fetch EveType for blueprint %s: %s", type_id, e)

    # Get active hangar divisions for this corporation
    hangar_divisions = {
        div.division_number: div 
        for div in config.hangar_divisions.filter(is_active=True)
    }

    # Process blueprint assets
    for asset in assets:
        if asset.type_id not in blueprint_types:
            continue
            
        blueprint_type = blueprint_types[asset.type_id]
        location_flag = getattr(asset, 'location_flag', None)
        
        # Only process if in a tracked hangar division
        if location_flag not in hangar_divisions:
            continue
            
        hangar_division = hangar_divisions[location_flag]
        
        # Extract blueprint metadata
        is_original = not getattr(asset, 'is_blueprint_copy', True)
        material_efficiency = getattr(asset, 'material_efficiency', 0) or 0
        time_efficiency = getattr(asset, 'time_efficiency', 0) or 0
        runs = getattr(asset, 'runs', 1) if not is_original else 1
        
        # Update or create inventory record
        BlueprintInventory.objects.update_or_create(
            corporation=config,
            blueprint_type=blueprint_type,
            location_division=hangar_division,
            defaults={
                'quantity': runs,
                'material_efficiency': material_efficiency,
                'time_efficiency': time_efficiency,
                'is_original': is_original,
            }
        )
    
    logger.info("Synced blueprint inventory for corp %s: %d blueprints found", 
                corporation_id, len(blueprint_types))


def is_blueprint_type_id(type_id: int) -> bool:
    """Check if a type_id is likely a blueprint based on EVE SDE knowledge."""
    # Blueprint items typically fall in certain category ranges
    # This is a simplified check - you may want to use eveuniverse for more accurate detection
    blueprint_categories = {9, 34, 39}  # Blueprint categories in EVE
    try:
        from eveuniverse.models import EveType
        eve_type = EveType.objects.filter(id=type_id).first()
        if eve_type:
            return eve_type.eve_group.category_id in blueprint_categories
    except:
        pass
    return False
