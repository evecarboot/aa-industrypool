from django.test import TestCase

from allianceauth.eveonline.models import EveCorporationInfo

from industrypool.forms import JobRequestForm
from industrypool.models import CorpHangarDivision, TrackedCorporation

from .factories import create_blueprint_type, create_corporation, create_user


class JobRequestFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.corporation = create_corporation()
        cls.tracked = TrackedCorporation.objects.create(corporation=cls.corporation)
        cls.division = CorpHangarDivision.objects.create(
            corporation=cls.tracked, division_number=1, name="Materials"
        )
        cls.other_corporation = create_corporation(98000002)
        cls.other_tracked = TrackedCorporation.objects.create(corporation=cls.other_corporation)
        cls.other_division = CorpHangarDivision.objects.create(
            corporation=cls.other_tracked, division_number=1, name="Other materials"
        )
        cls.blueprint_type = create_blueprint_type()
        cls.user, _ = create_user("manager")

    def _form(self, division):
        return JobRequestForm(
            data={
                "corporation": self.corporation.pk,
                "blueprint_type": self.blueprint_type.pk,
                "activity": "manufacturing",
                "runs": 1,
                "quantity": 1,
                "priority": 3,
                "hangar_divisions": [division.pk],
                "notes": "",
            },
            corporations=EveCorporationInfo.objects.all(),
        )

    def test_accepts_division_of_selected_corporation(self):
        form = self._form(self.division)
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_rejects_division_of_another_corporation(self):
        form = self._form(self.other_division)
        self.assertFalse(form.is_valid())

    def test_blueprint_choices_are_limited_to_blueprints(self):
        form = JobRequestForm(corporations=EveCorporationInfo.objects.all())
        self.assertEqual(
            list(form.fields["blueprint_type"].queryset), [self.blueprint_type]
        )
