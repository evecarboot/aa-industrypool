from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from industrypool.models import JobRequestStatus, TrackedIndustryJob

from .factories import (
    create_character,
    create_corporation,
    create_eve_type,
    create_job_request,
    create_tracked_corporation,
    create_user,
)


class TestJobRequest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.character = create_character(cls.corporation)
        cls.user = create_user(cls.character)
        cls.blueprint_type = create_eve_type()

    def _job(self, **kwargs):
        return create_job_request(
            self.corporation, self.blueprint_type, self.user, **kwargs
        )

    def test_claim_sets_status_and_timestamp(self):
        job = self._job()

        job.claim(self.user)

        self.assertEqual(job.status, JobRequestStatus.CLAIMED)
        self.assertEqual(job.claimed_by, self.user)
        self.assertIsNotNone(job.claimed_at)
        self.assertEqual(job.builder, self.user)

    def test_release_claim_returns_job_to_pool(self):
        job = self._job()
        job.claim(self.user)

        job.release_claim()

        self.assertTrue(job.is_open)
        self.assertIsNone(job.claimed_by)
        self.assertIsNone(job.claimed_at)

    def test_claim_is_not_expired_before_timeout(self):
        create_tracked_corporation(self.corporation, claim_timeout_hours=24)
        job = self._job()
        job.claim(self.user)

        self.assertFalse(job.is_claim_expired)

    def test_claim_is_expired_after_timeout(self):
        create_tracked_corporation(self.corporation, claim_timeout_hours=1)
        job = self._job()
        job.claim(self.user)
        job.claimed_at = timezone.now() - timedelta(hours=2)

        self.assertTrue(job.is_claim_expired)

    def test_claim_never_expires_when_timeout_disabled(self):
        create_tracked_corporation(self.corporation, claim_timeout_hours=0)
        job = self._job()
        job.claim(self.user)
        job.claimed_at = timezone.now() - timedelta(days=30)

        self.assertFalse(job.is_claim_expired)

    def test_claim_never_expires_without_tracked_corporation(self):
        job = self._job()
        job.claim(self.user)
        job.claimed_at = timezone.now() - timedelta(days=30)

        self.assertFalse(job.is_claim_expired)


class TestTrackedIndustryJob(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.character = create_character(cls.corporation)
        cls.blueprint_type = create_eve_type()

    def _tracked_job(self, start_offset_hours, end_offset_hours):
        now = timezone.now()
        return TrackedIndustryJob.objects.create(
            job_id=1,
            installer=self.character,
            corporation=self.corporation,
            activity_id=1,
            blueprint_type=self.blueprint_type,
            runs=1,
            start_date=now + timedelta(hours=start_offset_hours),
            end_date=now + timedelta(hours=end_offset_hours),
        )

    def test_progress_percent_is_capped_between_0_and_100(self):
        self.assertEqual(self._tracked_job(-4, -2).progress_percent, 100)

    def test_progress_percent_reports_elapsed_share(self):
        self.assertEqual(self._tracked_job(-1, 1).progress_percent, 50)

    def test_progress_percent_handles_zero_length_jobs(self):
        self.assertEqual(self._tracked_job(0, 0).progress_percent, 100)
