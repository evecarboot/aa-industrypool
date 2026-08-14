"""Populate job request materials from django-eveuniverse SDE data."""

from allianceauth.services.hooks import get_extension_logger
from eveuniverse.models import EveIndustryActivityMaterial

from .models import JobRequest, JobRequestMaterial
from .utils import activity_to_esi_id

logger = get_extension_logger(__name__)


def populate_job_materials(job_request: JobRequest) -> int:
    """Load blueprint materials for the job's activity and create JobRequestMaterial rows.

    Returns the number of materials created.
    """
    activity_id = activity_to_esi_id(job_request.activity)
    if activity_id is None:
        logger.warning("Unknown activity %s on job request %s", job_request.activity, job_request.pk)
        return 0

    try:
        EveIndustryActivityMaterial.objects.update_or_create_api(eve_type=job_request.blueprint_type)
    except Exception:
        logger.exception(
            "Failed to load industry materials for blueprint %s (job request %s)",
            job_request.blueprint_type_id,
            job_request.pk,
        )
        return 0

    materials = EveIndustryActivityMaterial.objects.filter(
        eve_type=job_request.blueprint_type,
        activity_id=activity_id,
    ).select_related("material_eve_type")

    created = 0
    for material in materials:
        _, was_created = JobRequestMaterial.objects.get_or_create(
            job_request=job_request,
            eve_type=material.material_eve_type,
            defaults={"quantity_required": material.quantity * job_request.runs},
        )
        if was_created:
            created += 1
    return created
