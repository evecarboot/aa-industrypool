"""Celery tasks for Industry Pool: ESI synchronisation and claim housekeeping."""

from celery import shared_task

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce
from esi.models import Token
from eveuniverse.models import EveType

from .blueprint_utils import release_jobs_waiting_on
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
BLUEPRINTS_SCOPES = ["esi-corporations.read_blueprints.v1"]
ESI_TASK_PRIORITY = 7

# ESI location flag -> division number mapping for corporation hangars
HANGAR_LOCATION_FLAGS = {f"CorpSAG{i}": i for i in range(1, 8)}


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

    jobs = esi.client.Industry.GetCorporationsCorporationIdIndustryJobs(
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
        for job_request in JobRequest.objects.filter(tracked_job=tracked_job):
            job_request.complete()
            release_jobs_waiting_on(job_request)


@shared_task(bind=True, base=QueueOnce)
def sync_corporation_blueprint_assets(self, corporation_id: int):
    """Pull corporation blueprints from ESI and refresh the blueprint inventory.

    Blueprints sitting in a tracked corp hangar division are aggregated per
    (corporation, blueprint type, division) and stored as BlueprintInventory rows.
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
        logger.error(
            "No valid ESI token with blueprints scope for director %s", config.director_character
        )
        return

    try:
        blueprints = esi.client.Corporation.GetCorporationsCorporationIdBlueprints(
            corporation_id=corporation_id, token=token
        ).results()
    except Exception:
        logger.exception("Failed to fetch blueprints for corp %s", corporation_id)
        return

    hangar_divisions = {
        div.division_number: div for div in config.hangar_divisions.filter(is_active=True)
    }
    totals = _aggregate_blueprints(blueprints or [], hangar_divisions)

    seen_pks = []
    for (type_id, division_number), stats in totals.items():
        try:
            blueprint_type, _ = EveType.objects.get_or_create_esi(id=type_id)
        except Exception:
            logger.warning("Failed to fetch EveType for blueprint %s", type_id)
            continue
        inventory, _ = BlueprintInventory.objects.update_or_create(
            corporation=config,
            blueprint_type=blueprint_type,
            location_division=hangar_divisions[division_number],
            defaults={
                "quantity": stats["quantity"],
                "material_efficiency": stats["material_efficiency"],
                "time_efficiency": stats["time_efficiency"],
                "is_original": stats["is_original"],
            },
        )
        seen_pks.append(inventory.pk)

    stale = BlueprintInventory.objects.filter(corporation=config).exclude(pk__in=seen_pks)
    removed = stale.count()
    stale.delete()

    logger.info(
        "Synced blueprint inventory for corp %s: %d entries, %d stale entries removed",
        corporation_id,
        len(seen_pks),
        removed,
    )


def _aggregate_blueprints(blueprints, hangar_divisions: dict) -> dict:
    """Aggregate ESI blueprint items per (type id, division number).

    ESI reports ``quantity`` as -1 for an original, -2 for a copy, or a positive stack size
    for untouched originals, and ``runs`` as -1 for originals. Originals win over copies for
    a given type/division, since a BPO can be used an unlimited number of times.
    """
    totals: dict[tuple[int, int], dict] = {}
    for blueprint in blueprints:
        division_number = HANGAR_LOCATION_FLAGS.get(blueprint.location_flag)
        if division_number is None or division_number not in hangar_divisions:
            continue

        is_original = blueprint.quantity != -2
        amount = max(blueprint.quantity, 1) if is_original else max(blueprint.runs, 0)
        key = (blueprint.type_id, division_number)
        stats = totals.get(key)
        if stats is None:
            totals[key] = {
                "quantity": amount,
                "material_efficiency": blueprint.material_efficiency,
                "time_efficiency": blueprint.time_efficiency,
                "is_original": is_original,
            }
            continue

        if is_original and not stats["is_original"]:
            # An original supersedes any copies counted so far for this type/division.
            stats.update(
                {
                    "quantity": amount,
                    "material_efficiency": blueprint.material_efficiency,
                    "time_efficiency": blueprint.time_efficiency,
                    "is_original": True,
                }
            )
        elif is_original == stats["is_original"]:
            stats["quantity"] += amount
            stats["material_efficiency"] = max(
                stats["material_efficiency"], blueprint.material_efficiency
            )
            stats["time_efficiency"] = max(stats["time_efficiency"], blueprint.time_efficiency)
    return totals
