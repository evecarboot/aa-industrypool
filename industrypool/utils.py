"""Shared helpers for Industry Pool."""

from allianceauth.eveonline.models import EveCorporationInfo

from .models import ACTIVITY_ESI_IDS


def user_corporations(user):
    """Corporations of all of a user's characters, used to scope what they can see/manage."""
    corp_ids = user.character_ownerships.values_list(
        "character__corporation_id", flat=True
    ).distinct()
    return EveCorporationInfo.objects.filter(corporation_id__in=corp_ids)


def user_character_ids(user) -> set[int]:
    """EVE character IDs owned by this AA user."""
    return set(
        user.character_ownerships.values_list("character__character_id", flat=True)
    )


def user_can_view_job(user, job) -> bool:
    if user.has_perm("industrypool.view_all_jobs"):
        return True
    return user_corporations(user).filter(pk=job.corporation_id).exists()


def user_can_manage_job(user, job) -> bool:
    if not user.has_perm("industrypool.manage_pool"):
        return False
    return user_can_view_job(user, job)


def user_can_claim_job(user, job) -> bool:
    if not user.has_perm("industrypool.claim_jobs") or not job.is_open:
        return False
    return user_can_view_job(user, job)


def activity_to_esi_id(activity: str) -> int | None:
    """Map a JobActivity value to the ESI/SDE activity id."""
    return ACTIVITY_ESI_IDS.get(activity)


def esi_id_to_activity(activity_id: int) -> str | None:
    """Map an ESI activity id back to a JobActivity value."""
    for activity, esi_id in ACTIVITY_ESI_IDS.items():
        if esi_id == activity_id:
            return activity
    return None
