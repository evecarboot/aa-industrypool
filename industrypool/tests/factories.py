"""Shared object factories for the industrypool test suite."""

from django.contrib.auth.models import Permission, User

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from eveuniverse.models import EveCategory, EveGroup, EveType

from industrypool.forms import BLUEPRINT_CATEGORY_ID

CORPORATION_ID = 98000001


def create_corporation(corporation_id: int = CORPORATION_ID) -> EveCorporationInfo:
    return EveCorporationInfo.objects.create(
        corporation_id=corporation_id,
        corporation_name=f"Corp {corporation_id}",
        corporation_ticker="CORP",
        member_count=10,
    )


def create_blueprint_type(type_id: int = 1234) -> EveType:
    category, _ = EveCategory.objects.get_or_create(
        id=BLUEPRINT_CATEGORY_ID, defaults={"name": "Blueprint", "published": True}
    )
    group, _ = EveGroup.objects.get_or_create(
        id=105,
        defaults={"name": "Blueprints", "published": True, "eve_category": category},
    )
    return EveType.objects.create(
        id=type_id,
        name=f"Test Blueprint {type_id}",
        published=True,
        enabled_sections=0,
        eve_group=group,
    )


def create_user(username: str, corporation_id: int = CORPORATION_ID, character_id: int = 90001):
    user = User.objects.create_user(username, f"{username}@example.com", "password")
    character = EveCharacter.objects.create(
        character_id=character_id,
        character_name=username,
        corporation_id=corporation_id,
        corporation_name=f"Corp {corporation_id}",
        corporation_ticker="CORP",
    )
    CharacterOwnership.objects.create(
        user=user, character=character, owner_hash=f"hash{character_id}"
    )
    user.profile.main_character = character
    user.profile.save()
    for codename in ("basic_access", "manage_pool", "claim_jobs"):
        user.user_permissions.add(
            Permission.objects.get(codename=codename, content_type__app_label="industrypool")
        )
    return User.objects.get(pk=user.pk), character
