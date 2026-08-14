from django import forms
from django.contrib.auth import get_user_model

from allianceauth.eveonline.models import EveCorporationInfo

from .models import CorpHangarDivision, JobRequest

User = get_user_model()


class JobRequestForm(forms.ModelForm):
    use_bpo_directly = forms.BooleanField(
        required=False,
        initial=False,
        label="Use BPO directly (skip copy jobs)",
        help_text="If the corp has a Blueprint Original, use it directly for manufacturing "
                  "instead of creating copy jobs first. Only applies to manufacturing activities.",
    )

    class Meta:
        model = JobRequest
        fields = [
            "corporation",
            "blueprint_type",
            "activity",
            "runs",
            "quantity",
            "hangar_divisions",
            "priority",
            "assigned_to",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "hangar_divisions": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, corporations=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].required = False
        self.fields["assigned_to"].help_text = "Leave blank to post this job to the open pool"
        self.fields["hangar_divisions"].required = False
        corp_qs = corporations if corporations is not None else EveCorporationInfo.objects.all()
        corp_ids = [c.corporation_id for c in corp_qs]
        self.fields["hangar_divisions"].queryset = CorpHangarDivision.objects.filter(
            is_active=True,
            corporation__corporation__corporation_id__in=corp_ids,
        )
        if corporations is not None:
            self.fields["corporation"].queryset = EveCorporationInfo.objects.filter(
                pk__in=[c.pk for c in corporations]
            )
            self.fields["assigned_to"].queryset = User.objects.filter(
                character_ownerships__character__corporation_id__in=corp_ids
            ).distinct()

    def clean(self):
        cleaned = super().clean()
        corporation = cleaned.get("corporation")
        hangar_divisions = cleaned.get("hangar_divisions")
        assigned_to = cleaned.get("assigned_to")

        if corporation and hangar_divisions:
            invalid = [
                division
                for division in hangar_divisions
                if division.corporation.corporation_id != corporation.corporation_id
            ]
            if invalid:
                raise forms.ValidationError(
                    "Selected hangar divisions must belong to the chosen corporation."
                )

        if assigned_to and corporation:
            user_corp_ids = assigned_to.character_ownerships.values_list(
                "character__corporation_id", flat=True
            )
            if corporation.corporation_id not in set(user_corp_ids):
                raise forms.ValidationError(
                    "Assigned user must have a character in the selected corporation."
                )

        return cleaned
