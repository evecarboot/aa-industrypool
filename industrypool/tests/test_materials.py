from unittest.mock import patch

from django.test import TestCase

from eveuniverse.models import EveIndustryActivity, EveIndustryActivityMaterial

from industrypool.materials import populate_job_materials
from industrypool.models import JobActivity, JobRequestMaterial
from industrypool.utils import activity_esi_ids

from .factories import (
    create_character,
    create_corporation,
    create_eve_type,
    create_job_request,
    create_user,
)


class TestPopulateJobMaterials(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.character = create_character(cls.corporation)
        cls.user = create_user(cls.character)
        cls.blueprint_type = create_eve_type()
        cls.material_type = create_eve_type(type_id=34, name="Tritanium")

    def _add_sde_material(self, activity_id, quantity=100):
        EveIndustryActivityMaterial.objects.create(
            eve_type=self.blueprint_type,
            activity=EveIndustryActivity.objects.get(pk=activity_id),
            material_eve_type=self.material_type,
            quantity=quantity,
        )

    def test_creates_materials_scaled_by_runs(self):
        self._add_sde_material(1, quantity=100)
        job = create_job_request(
            self.corporation, self.blueprint_type, self.user, runs=3
        )

        with patch.object(
            EveIndustryActivityMaterial.objects, "update_or_create_api", return_value=None
        ):
            created = populate_job_materials(job)

        self.assertEqual(created, 1)
        material = JobRequestMaterial.objects.get(job_request=job)
        self.assertEqual(material.eve_type, self.material_type)
        self.assertEqual(material.quantity_required, 300)

    def test_reaction_materials_stored_under_the_legacy_activity_id_are_found(self):
        self._add_sde_material(9, quantity=50)
        job = create_job_request(
            self.corporation,
            self.blueprint_type,
            self.user,
            activity=JobActivity.REACTION,
        )

        with patch.object(
            EveIndustryActivityMaterial.objects, "update_or_create_api", return_value=None
        ):
            created = populate_job_materials(job)

        self.assertEqual(created, 1)
        self.assertEqual(activity_esi_ids(JobActivity.REACTION), [11, 9])

    def test_materials_of_other_activities_are_ignored(self):
        self._add_sde_material(8)
        job = create_job_request(self.corporation, self.blueprint_type, self.user)

        with patch.object(
            EveIndustryActivityMaterial.objects, "update_or_create_api", return_value=None
        ):
            created = populate_job_materials(job)

        self.assertEqual(created, 0)

    def test_sde_lookup_failures_do_not_raise(self):
        job = create_job_request(self.corporation, self.blueprint_type, self.user)

        with patch.object(
            EveIndustryActivityMaterial.objects,
            "update_or_create_api",
            side_effect=OSError("boom"),
        ):
            self.assertEqual(populate_job_materials(job), 0)
