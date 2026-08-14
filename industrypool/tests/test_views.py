from django.test import TestCase
from django.urls import reverse

from industrypool.models import CorpHangarDivision, JobRequest, JobRequestStatus, TrackedCorporation

from .factories import create_blueprint_type, create_corporation, create_user


class ViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.tracked = TrackedCorporation.objects.create(corporation=cls.corporation)
        cls.division = CorpHangarDivision.objects.create(
            corporation=cls.tracked, division_number=1, name="Materials"
        )
        cls.blueprint_type = create_blueprint_type()
        cls.user, _ = create_user("manager")

    def setUp(self):
        self.client.force_login(self.user)

    def _job(self, **kwargs):
        return JobRequest.objects.create(
            corporation=self.corporation,
            blueprint_type=self.blueprint_type,
            created_by=self.user,
            **kwargs,
        )

    def test_pages_render(self):
        job = self._job()
        for url in (
            reverse("industrypool:pool_list"),
            reverse("industrypool:my_jobs"),
            reverse("industrypool:job_create"),
            reverse("industrypool:job_detail", args=[job.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_claim(self):
        job = self._job()
        self.client.post(reverse("industrypool:job_claim", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.status, JobRequestStatus.CLAIMED)

    def test_open_job_can_be_cancelled(self):
        job = self._job()
        self.client.post(reverse("industrypool:job_cancel", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.status, JobRequestStatus.CANCELLED)

    def test_completed_job_cannot_be_cancelled(self):
        job = self._job(status=JobRequestStatus.COMPLETED)
        self.client.post(reverse("industrypool:job_cancel", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.status, JobRequestStatus.COMPLETED)

    def test_create_job_with_hangar_division(self):
        response = self.client.post(
            reverse("industrypool:job_create"),
            data={
                "corporation": self.corporation.pk,
                "blueprint_type": self.blueprint_type.pk,
                "activity": "manufacturing",
                "runs": 1,
                "quantity": 1,
                "priority": 3,
                "hangar_divisions": [self.division.pk],
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        job = JobRequest.objects.get()
        self.assertEqual(list(job.hangar_divisions.all()), [self.division])
        self.assertEqual(job.status, JobRequestStatus.OPEN)
