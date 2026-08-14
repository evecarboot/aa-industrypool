"""Celery tasks to sync ESI corporation industry jobs against Industry Pool job requests."""

from celery import shared_task

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce
from esi.models import Token
from eveuniverse.models import EveType

from .models import CorpHangarDivision, JobRequest, JobRequestStatus, TrackedCorporation, TrackedIndustryJob
from .providers import esi
from .utils import esi_id_to_activity

logger = get_extension_logger(__name__)

INDUSTRY_JOBS_SCOPES = ["esi-industry.read_corporation_jobs.v1"]
DIVISIONS_SCOPES = ["esi-corporations.read_divisions.v1"]
ESI_TASK_PRIORITY = 7


@shared_task
def sync_all_corporation_industry_jobs():
    """Kick off a sync task for every actively tracked corporation."""
    for config in TrackedCorporation.objects.filter(is_active=True):
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
    for config in TrackedCorporation.objects.filter(is_active=True):
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
        matching_request.tracked_job = tracked_job
        matching_request.status = JobRequestStatus.IN_PROGRESS
        matching_request.save(update_fields=["tracked_job", "status", "updated_at"])

    if job.status == "delivered":
        JobRequest.objects.filter(tracked_job=tracked_job).update(status=JobRequestStatus.COMPLETED)
