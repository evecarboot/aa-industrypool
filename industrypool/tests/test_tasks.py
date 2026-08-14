from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from industrypool.models import (
    JobActivity,
    JobRequest,
    JobRequestStatus,
    TrackedIndustryJob,
)
from industrypool.tasks import _update_tracked_job, release_stale_claims

from .factories import (
    create_character,
    create_corporation,
    create_eve_type,
    create_job_request,
    create_tracked_corporation,
    create_user,
)

TASKS_PATH = "industrypool.tasks"


class EsiJobStub:
    """Stand-in for an ESI corporation industry job object."""

    def __init__(self, blueprint_type_id, installer_id, **kwargs):
        now = timezone.now()
        self.job_id = kwargs.get("job_id", 5001)
        self.blueprint_type_id = blueprint_type_id
        self.installer_id = installer_id
        self.activity_id = kwargs.get("activity_id", 1)
        self.runs = kwargs.get("runs", 1)
        self.start_date = kwargs.get("start_date", now - timedelta(hours=1))
        self.end_date = kwargs.get("end_date", now + timedelta(hours=1))
        self.pause_date = kwargs.get("pause_date")
        self.status = kwargs.get("status", "active")


class TestUpdateTrackedJob(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.character = create_character(cls.corporation)
        cls.user = create_user(cls.character)
        cls.blueprint_type = create_eve_type()
        cls.config = create_tracked_corporation(cls.corporation, cls.character)

    def setUp(self):
        patcher_type = patch(
            f"{TASKS_PATH}.EveType.objects.get_or_create_esi",
            return_value=(self.blueprint_type, False),
        )
        patcher_character = patch(
            f"{TASKS_PATH}._get_or_create_character", return_value=self.character
        )
        self.addCleanup(patcher_type.stop)
        self.addCleanup(patcher_character.stop)
        patcher_type.start()
        patcher_character.start()

    def test_creates_tracked_job_from_esi_job(self):
        job = EsiJobStub(self.blueprint_type.id, self.character.character_id)

        _update_tracked_job(self.config, job)

        tracked_job = TrackedIndustryJob.objects.get(job_id=job.job_id)
        self.assertEqual(tracked_job.installer, self.character)
        self.assertEqual(tracked_job.corporation, self.corporation)
        self.assertEqual(tracked_job.runs, 1)
        self.assertEqual(tracked_job.status, "active")

    def test_matches_claimed_job_request_of_the_installer_owner(self):
        job_request = create_job_request(
            self.corporation,
            self.blueprint_type,
            self.user,
            activity=JobActivity.MANUFACTURING,
            runs=1,
        )
        job_request.claim(self.user)

        _update_tracked_job(
            self.config, EsiJobStub(self.blueprint_type.id, self.character.character_id)
        )

        job_request.refresh_from_db()
        self.assertEqual(job_request.status, JobRequestStatus.IN_PROGRESS)
        self.assertIsNotNone(job_request.tracked_job)

    def test_does_not_match_job_request_of_another_user(self):
        other_character = create_character(
            self.corporation, character_id=1002, name="Other Character"
        )
        other_user = create_user(other_character)
        job_request = create_job_request(
            self.corporation, self.blueprint_type, self.user, runs=1
        )
        job_request.claim(other_user)

        _update_tracked_job(
            self.config, EsiJobStub(self.blueprint_type.id, self.character.character_id)
        )

        job_request.refresh_from_db()
        self.assertEqual(job_request.status, JobRequestStatus.CLAIMED)
        self.assertIsNone(job_request.tracked_job)

    def test_does_not_rematch_an_already_matched_tracked_job(self):
        matched = create_job_request(
            self.corporation, self.blueprint_type, self.user, runs=1
        )
        matched.claim(self.user)
        esi_job = EsiJobStub(self.blueprint_type.id, self.character.character_id)
        _update_tracked_job(self.config, esi_job)

        other_request = create_job_request(
            self.corporation, self.blueprint_type, self.user, runs=1
        )
        other_request.claim(self.user)
        _update_tracked_job(self.config, esi_job)

        other_request.refresh_from_db()
        self.assertIsNone(other_request.tracked_job)
        self.assertEqual(JobRequest.objects.filter(tracked_job__isnull=False).count(), 1)

    def test_delivered_job_completes_the_job_request(self):
        job_request = create_job_request(
            self.corporation, self.blueprint_type, self.user, runs=1
        )
        job_request.claim(self.user)
        esi_job = EsiJobStub(self.blueprint_type.id, self.character.character_id)
        _update_tracked_job(self.config, esi_job)

        esi_job.status = "delivered"
        _update_tracked_job(self.config, esi_job)

        job_request.refresh_from_db()
        self.assertEqual(job_request.status, JobRequestStatus.COMPLETED)

    def test_unknown_activity_id_is_not_matched(self):
        job_request = create_job_request(
            self.corporation, self.blueprint_type, self.user, runs=1
        )
        job_request.claim(self.user)

        _update_tracked_job(
            self.config,
            EsiJobStub(
                self.blueprint_type.id, self.character.character_id, activity_id=42
            ),
        )

        job_request.refresh_from_db()
        self.assertIsNone(job_request.tracked_job)


class TestReleaseStaleClaims(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.character = create_character(cls.corporation)
        cls.user = create_user(cls.character)
        cls.blueprint_type = create_eve_type()
        create_tracked_corporation(cls.corporation, cls.character, claim_timeout_hours=1)

    def test_releases_expired_claims_only(self):
        expired = create_job_request(self.corporation, self.blueprint_type, self.user)
        expired.claim(self.user)
        JobRequest.objects.filter(pk=expired.pk).update(
            claimed_at=timezone.now() - timedelta(hours=2)
        )
        fresh = create_job_request(self.corporation, self.blueprint_type, self.user)
        fresh.claim(self.user)

        with patch(f"{TASKS_PATH}.notify"):
            release_stale_claims()

        expired.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(expired.status, JobRequestStatus.OPEN)
        self.assertIsNone(expired.claimed_by)
        self.assertEqual(fresh.status, JobRequestStatus.CLAIMED)

    def test_notifies_the_claimant(self):
        job = create_job_request(self.corporation, self.blueprint_type, self.user)
        job.claim(self.user)
        JobRequest.objects.filter(pk=job.pk).update(
            claimed_at=timezone.now() - timedelta(hours=2)
        )

        with patch(f"{TASKS_PATH}.notify") as mock_notify:
            release_stale_claims()

        self.assertTrue(mock_notify.called)
        self.assertEqual(mock_notify.call_args[0][0], self.user)
