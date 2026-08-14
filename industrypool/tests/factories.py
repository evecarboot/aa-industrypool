"""Object factories for the Industry Pool test suite."""

from django.contrib.auth.models import Permission, User

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from eveuniverse.models import EveCategory, EveGroup, EveType

from industrypool.models import (
    CorpHangarDivision,
    JobActivity,
    JobRequest,
    TrackedCorporation,
)


def create_corporation(corporation_id=2001, name="Test Corp") -> EveCorporationInfo:
    return EveCorporationInfo.objects.create(
        corporation_id=corporation_id,
        corporation_name=name,
        corporation_ticker=name[:4].upper(),
        member_count=10,
    )


def create_character(
    corporation: EveCorporationInfo, character_id=1001, name="Test Character"
) -> EveCharacter:
    return EveCharacter.objects.create(
        character_id=character_id,
        character_name=name,
        corporation_id=corporation.corporation_id,
        corporation_name=corporation.corporation_name,
        corporation_ticker=corporation.corporation_ticker,
    )


def create_user(character: EveCharacter, permissions=None, username=None) -> User:
    user = User.objects.create_user(
        username or character.character_name.replace(" ", "_")
    )
    CharacterOwnership.objects.create(
        user=user, character=character, owner_hash=f"hash-{character.character_id}"
    )
    user.profile.main_character = character
    user.profile.save()
    for codename in permissions or []:
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="industrypool", codename=codename
            )
        )
    return User.objects.get(pk=user.pk)  # reset the permission cache


def create_eve_type(type_id=1000, name="Test Blueprint") -> EveType:
    category = EveCategory.objects.get_or_create(
        id=9, defaults={"name": "Blueprint", "published": True}
    )[0]
    group = EveGroup.objects.get_or_create(
        id=105,
        defaults={"name": "Blueprints", "eve_category": category, "published": True},
    )[0]
    return EveType.objects.create(
        id=type_id, name=name, eve_group=group, published=True
    )


def create_tracked_corporation(
    corporation: EveCorporationInfo, director: EveCharacter = None, **kwargs
) -> TrackedCorporation:
    return TrackedCorporation.objects.create(
        corporation=corporation, director_character=director, **kwargs
    )


def create_hangar_division(
    config: TrackedCorporation, division_number=1, name="Materials", **kwargs
) -> CorpHangarDivision:
    return CorpHangarDivision.objects.create(
        corporation=config, division_number=division_number, name=name, **kwargs
    )


def create_job_request(
    corporation: EveCorporationInfo,
    blueprint_type: EveType,
    created_by: User,
    **kwargs,
) -> JobRequest:
    kwargs.setdefault("activity", JobActivity.MANUFACTURING)
    kwargs.setdefault("runs", 1)
    return JobRequest.objects.create(
        corporation=corporation,
        blueprint_type=blueprint_type,
        created_by=created_by,
        **kwargs,
    )
