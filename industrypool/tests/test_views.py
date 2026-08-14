from django.test import TestCase
from django.urls import reverse

from industrypool.models import JobRequestStatus

from .factories import (
    create_character,
    create_corporation,
    create_eve_type,
    create_job_request,
    create_user,
)


class TestViews(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.other_corporation = create_corporation(2002, "Other Corp")
        cls.character = create_character(cls.corporation)
        cls.other_character = create_character(
            cls.other_corporation, character_id=1002, name="Other Character"
        )
        cls.blueprint_type = create_eve_type()

    def test_pool_list_hides_jobs_of_other_corporations(self):
        owner = create_user(self.character, ["basic_access"])
        outsider = create_user(self.other_character, ["basic_access"])
        job = create_job_request(self.corporation, self.blueprint_type, owner)

        self.client.force_login(outsider)
        response = self.client.get(reverse("industrypool:pool_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(job, response.context["jobs"])

        self.client.force_login(owner)
        response = self.client.get(reverse("industrypool:pool_list"))
        self.assertIn(job, response.context["jobs"])

    def test_my_jobs_lists_claimed_and_assigned_jobs_once(self):
        user = create_user(self.character, ["basic_access"])
        claimed = create_job_request(self.corporation, self.blueprint_type, user)
        claimed.claim(user)
        assigned = create_job_request(self.corporation, self.blueprint_type, user)
        assigned.assign(user)
        both = create_job_request(self.corporation, self.blueprint_type, user)
        both.assign(user)
        both.claim(user)
        create_job_request(self.corporation, self.blueprint_type, user)

        self.client.force_login(user)
        response = self.client.get(reverse("industrypool:my_jobs"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(job.pk for job in response.context["jobs"]),
            sorted([claimed.pk, assigned.pk, both.pk]),
        )

    def test_job_detail_denied_for_other_corporation(self):
        owner = create_user(self.character, ["basic_access"])
        outsider = create_user(self.other_character, ["basic_access"])
        job = create_job_request(self.corporation, self.blueprint_type, owner)

        self.client.force_login(outsider)
        response = self.client.get(reverse("industrypool:job_detail", args=[job.pk]))

        self.assertEqual(response.status_code, 403)

    def test_claiming_a_job_marks_it_claimed(self):
        user = create_user(self.character, ["basic_access", "claim_jobs"])
        job = create_job_request(self.corporation, self.blueprint_type, user)

        self.client.force_login(user)
        response = self.client.post(reverse("industrypool:job_claim", args=[job.pk]))

        job.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(job.status, JobRequestStatus.CLAIMED)
        self.assertEqual(job.claimed_by, user)

    def test_claiming_an_already_claimed_job_is_rejected(self):
        owner = create_user(self.character, ["basic_access", "claim_jobs"])
        other = create_user(
            create_character(self.corporation, character_id=1003, name="Third Character"),
            ["basic_access", "claim_jobs"],
        )
        job = create_job_request(self.corporation, self.blueprint_type, owner)
        job.claim(owner)

        self.client.force_login(other)
        self.client.post(reverse("industrypool:job_claim", args=[job.pk]))

        job.refresh_from_db()
        self.assertEqual(job.claimed_by, owner)

    def test_outsider_cannot_claim_job_of_another_corporation(self):
        owner = create_user(self.character, ["basic_access"])
        outsider = create_user(self.other_character, ["basic_access", "claim_jobs"])
        job = create_job_request(self.corporation, self.blueprint_type, owner)

        self.client.force_login(outsider)
        response = self.client.post(reverse("industrypool:job_claim", args=[job.pk]))

        job.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(job.status, JobRequestStatus.OPEN)

    def test_cancel_requires_manage_permission(self):
        user = create_user(self.character, ["basic_access"])
        job = create_job_request(self.corporation, self.blueprint_type, user)

        self.client.force_login(user)
        response = self.client.post(reverse("industrypool:job_cancel", args=[job.pk]))

        job.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(job.status, JobRequestStatus.OPEN)

    def test_manager_can_cancel_job(self):
        user = create_user(self.character, ["basic_access", "manage_pool"])
        job = create_job_request(self.corporation, self.blueprint_type, user)

        self.client.force_login(user)
        self.client.post(reverse("industrypool:job_cancel", args=[job.pk]))

        job.refresh_from_db()
        self.assertEqual(job.status, JobRequestStatus.CANCELLED)
