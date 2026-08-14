from django import forms

from allianceauth.eveonline.models import EveCorporationInfo

from .models import CorpHangarDivision, JobRequest


class JobRequestForm(forms.ModelForm):
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
        self.fields["hangar_divisions"].queryset = CorpHangarDivision.objects.filter(
            is_active=True,
            corporation__corporation__in=corporations if corporations is not None else EveCorporationInfo.objects.all(),
        )
        if corporations is not None:
            self.fields["corporation"].queryset = EveCorporationInfo.objects.filter(
                pk__in=[c.pk for c in corporations]
            )
