from django.test import TestCase

from industrypool.models import JobActivity
from industrypool.utils import (
    activity_to_esi_id,
    esi_id_to_activity,
    user_can_claim_job,
    user_can_view_job,
    user_corporations,
)

from .factories import (
    create_character,
    create_corporation,
    create_eve_type,
    create_job_request,
    create_user,
)


class TestActivityMapping(TestCase):
    def test_maps_activities_to_current_sde_ids(self):
        self.assertEqual(activity_to_esi_id(JobActivity.MANUFACTURING), 1)
        self.assertEqual(activity_to_esi_id(JobActivity.RESEARCH_TE), 3)
        self.assertEqual(activity_to_esi_id(JobActivity.RESEARCH_ME), 4)
        self.assertEqual(activity_to_esi_id(JobActivity.COPYING), 5)
        self.assertEqual(activity_to_esi_id(JobActivity.INVENTION), 8)
        self.assertEqual(activity_to_esi_id(JobActivity.REACTION), 11)

    def test_maps_ids_back_to_activities(self):
        for activity in JobActivity:
            esi_id = activity_to_esi_id(activity)
            self.assertEqual(esi_id_to_activity(esi_id), activity)

    def test_maps_legacy_reaction_id_to_reaction(self):
        self.assertEqual(esi_id_to_activity(9), JobActivity.REACTION)

    def test_returns_none_for_unknown_ids(self):
        self.assertIsNone(esi_id_to_activity(42))
        self.assertIsNone(activity_to_esi_id("nonsense"))


class TestPermissionHelpers(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.other_corporation = create_corporation(2002, "Other Corp")
        cls.character = create_character(cls.corporation)
        cls.other_character = create_character(
            cls.other_corporation, character_id=1002, name="Other Character"
        )
        cls.blueprint_type = create_eve_type()

    def test_user_corporations_lists_owned_character_corporations(self):
        user = create_user(self.character)

        self.assertEqual(list(user_corporations(user)), [self.corporation])

    def test_member_of_other_corporation_cannot_view_job(self):
        owner = create_user(self.character, ["basic_access"])
        outsider = create_user(self.other_character, ["basic_access"])
        job = create_job_request(self.corporation, self.blueprint_type, owner)

        self.assertTrue(user_can_view_job(owner, job))
        self.assertFalse(user_can_view_job(outsider, job))

    def test_view_all_jobs_permission_grants_cross_corporation_view(self):
        owner = create_user(self.character, ["basic_access"])
        outsider = create_user(self.other_character, ["basic_access", "view_all_jobs"])
        job = create_job_request(self.corporation, self.blueprint_type, owner)

        self.assertTrue(user_can_view_job(outsider, job))

    def test_claiming_requires_permission_and_open_job(self):
        owner = create_user(self.character, ["basic_access", "claim_jobs"])
        job = create_job_request(self.corporation, self.blueprint_type, owner)

        self.assertTrue(user_can_claim_job(owner, job))

        job.claim(owner)
        self.assertFalse(user_can_claim_job(owner, job))
