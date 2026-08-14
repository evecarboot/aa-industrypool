from unittest.mock import patch

from django.test import TestCase

from industrypool.blueprint_utils import create_smart_job_request, release_jobs_waiting_on
from industrypool.models import (
    BlueprintInventory,
    CorpHangarDivision,
    JobActivity,
    JobRequestStatus,
    TrackedCorporation,
)

from .factories import create_blueprint_type, create_corporation, create_user


@patch("industrypool.blueprint_utils.populate_job_materials", lambda job: 0)
class SmartJobRequestTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.tracked = TrackedCorporation.objects.create(corporation=cls.corporation)
        cls.division = CorpHangarDivision.objects.create(
            corporation=cls.tracked, division_number=1, name="Blueprints"
        )
        cls.blueprint_type = create_blueprint_type()
        cls.user, _ = create_user("manager")

    def _create(self, runs=5, divisions=None):
        return create_smart_job_request(
            blueprint_type=self.blueprint_type,
            quantity=runs,
            activity=JobActivity.MANUFACTURING,
            runs=runs,
            hangar_divisions=[self.division] if divisions is None else divisions,
            corporation=self.corporation,
            priority=3,
            assigned_to=None,
            notes="",
            created_by=self.user,
        )

    def test_original_blueprint_needs_no_copy_job(self):
        BlueprintInventory.objects.create(
            corporation=self.tracked,
            blueprint_type=self.blueprint_type,
            location_division=self.division,
            quantity=1,
            is_original=True,
        )
        job, copy_jobs = self._create()
        self.assertEqual((job.status, copy_jobs), (JobRequestStatus.OPEN, []))

    def test_missing_copies_create_one_copy_job(self):
        BlueprintInventory.objects.create(
            corporation=self.tracked,
            blueprint_type=self.blueprint_type,
            location_division=self.division,
            quantity=2,
            is_original=False,
        )
        job, copy_jobs = self._create(runs=5)
        self.assertEqual(job.status, JobRequestStatus.WAITING_FOR_COPIES)
        self.assertEqual(len(copy_jobs), 1)
        self.assertEqual((copy_jobs[0].activity, copy_jobs[0].runs), (JobActivity.COPYING, 3))

    def test_job_is_not_left_waiting_without_a_copy_job(self):
        job, copy_jobs = self._create()
        self.assertEqual((job.status, copy_jobs), (JobRequestStatus.OPEN, []))

    def test_completed_copy_job_releases_the_waiting_job(self):
        BlueprintInventory.objects.create(
            corporation=self.tracked,
            blueprint_type=self.blueprint_type,
            location_division=self.division,
            quantity=2,
            is_original=False,
        )
        job, copy_jobs = self._create(runs=5)
        copy_jobs[0].complete()

        released = release_jobs_waiting_on(copy_jobs[0])
        job.refresh_from_db()
        self.assertEqual([j.pk for j in released], [job.pk])
        self.assertEqual(job.status, JobRequestStatus.OPEN)
        self.assertTrue(job.dependencies.get().is_satisfied)
