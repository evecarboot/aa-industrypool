from types import SimpleNamespace

from django.test import TestCase

from industrypool.models import CorpHangarDivision, TrackedCorporation
from industrypool.tasks import _aggregate_blueprints

from .factories import create_corporation


def blueprint(type_id, location_flag, quantity, runs, me=0, te=0):
    """An ESI blueprint item: quantity -1 = original, -2 = copy, >0 = stack of originals."""
    return SimpleNamespace(
        type_id=type_id,
        location_flag=location_flag,
        quantity=quantity,
        runs=runs,
        material_efficiency=me,
        time_efficiency=te,
    )


class AggregateBlueprintsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        tracked = TrackedCorporation.objects.create(corporation=create_corporation())
        cls.division = CorpHangarDivision.objects.create(
            corporation=tracked, division_number=1, name="Blueprints"
        )
        cls.divisions = {1: cls.division}

    def test_original_is_detected_and_runs_are_not_negative(self):
        totals = _aggregate_blueprints([blueprint(1234, "CorpSAG1", -1, -1, me=10, te=20)], self.divisions)
        self.assertEqual(
            totals[(1234, 1)],
            {"quantity": 1, "material_efficiency": 10, "time_efficiency": 20, "is_original": True},
        )

    def test_copies_are_summed_by_remaining_runs(self):
        totals = _aggregate_blueprints(
            [
                blueprint(1234, "CorpSAG1", -2, 5, me=2),
                blueprint(1234, "CorpSAG1", -2, 3, me=4),
            ],
            self.divisions,
        )
        self.assertEqual(totals[(1234, 1)]["quantity"], 8)
        self.assertFalse(totals[(1234, 1)]["is_original"])
        self.assertEqual(totals[(1234, 1)]["material_efficiency"], 4)

    def test_original_supersedes_copies(self):
        totals = _aggregate_blueprints(
            [blueprint(1234, "CorpSAG1", -2, 5), blueprint(1234, "CorpSAG1", 3, -1)],
            self.divisions,
        )
        self.assertEqual(totals[(1234, 1)]["quantity"], 3)
        self.assertTrue(totals[(1234, 1)]["is_original"])

    def test_untracked_locations_are_ignored(self):
        totals = _aggregate_blueprints(
            [blueprint(1234, "CorpSAG5", -1, -1), blueprint(1234, "Hangar", -1, -1)],
            self.divisions,
        )
        self.assertEqual(totals, {})
