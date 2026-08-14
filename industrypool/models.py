"""Models for the Industry Pool app."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from eveuniverse.models import EveType

User = get_user_model()


class General(models.Model):
    """Meta model used only to attach app-level permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access the Industry Pool app"),
            ("manage_pool", "Can create, assign and cancel job requests"),
            ("claim_jobs", "Can claim open job requests from the pool"),
            ("view_all_jobs", "Can view all job requests and industry jobs across the corporation"),
        )


class JobActivity(models.TextChoices):
    MANUFACTURING = "manufacturing", "Manufacturing"
    REACTION = "reaction", "Reaction"
    INVENTION = "invention", "Invention"
    RESEARCH_ME = "research_me", "Material Efficiency Research"
    RESEARCH_TE = "research_te", "Time Efficiency Research"
    COPYING = "copying", "Copying"


# ESI / SDE industry activity ids (see EveIndustryActivity).
ACTIVITY_ESI_IDS: dict[str, int] = {
    JobActivity.MANUFACTURING: 1,
    JobActivity.RESEARCH_TE: 3,
    JobActivity.RESEARCH_ME: 4,
    JobActivity.COPYING: 5,
    JobActivity.INVENTION: 11,
    JobActivity.REACTION: 25,
}


class JobRequestStatus(models.TextChoices):
    OPEN = "open", "Open"
    ASSIGNED = "assigned", "Assigned"
    CLAIMED = "claimed", "Claimed"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    WAITING_FOR_COPIES = "waiting_for_copies", "Waiting for Copies"


class TrackedCorporation(models.Model):
    """A corporation configured for Industry Pool, with a director token used for ESI syncs."""

    corporation = models.OneToOneField(
        EveCorporationInfo, on_delete=models.CASCADE, related_name="industrypool_config"
    )
    director_character = models.ForeignKey(
        EveCharacter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Character with a director-level ESI token used to pull corp industry jobs",
    )
    is_active = models.BooleanField(default=True)
    claim_timeout_hours = models.PositiveIntegerField(
        default=24,
        help_text=(
            "Hours a member has to start building after claiming a job before it's "
            "automatically returned to the open pool. Set to 0 to disable."
        ),
    )

    class Meta:
        default_permissions = ()
        verbose_name = "Tracked Corporation"
        verbose_name_plural = "Tracked Corporations"

    def __str__(self) -> str:
        return str(self.corporation)


class CorpHangarDivision(models.Model):
    """A corp hangar division admins have made available as a material source for job requests.

    ``name`` can be synced from ESI (esi-corporations.read_divisions.v1) or set manually by an admin.
    """

    corporation = models.ForeignKey(
        TrackedCorporation, on_delete=models.CASCADE, related_name="hangar_divisions"
    )
    division_number = models.PositiveSmallIntegerField(
        help_text="Corp hangar division, 1-7",
        validators=[MinValueValidator(1), MaxValueValidator(7)],
    )
    name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True, help_text="Available for selection on new job requests")

    class Meta:
        default_permissions = ()
        unique_together = ("corporation", "division_number")
        ordering = ["division_number"]
        verbose_name = "Corp Hangar Division"
        verbose_name_plural = "Corp Hangar Divisions"

    def __str__(self) -> str:
        label = self.name or f"Division {self.division_number}"
        return f"{self.corporation.corporation} - {label}"


class TrackedIndustryJob(models.Model):
    """Mirrors an ESI corporation industry job so progress can be shown against a JobRequest."""

    job_id = models.PositiveBigIntegerField(unique=True)
    installer = models.ForeignKey(
        EveCharacter, on_delete=models.CASCADE, related_name="industrypool_jobs"
    )
    corporation = models.ForeignKey(
        EveCorporationInfo, on_delete=models.CASCADE, related_name="industrypool_tracked_jobs"
    )

    activity_id = models.PositiveSmallIntegerField()
    blueprint_type = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="+")
    runs = models.PositiveIntegerField()

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    pause_date = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, default="active")

    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"Job {self.job_id} ({self.status})"

    @property
    def progress_percent(self) -> int:
        total = (self.end_date - self.start_date).total_seconds()
        if total <= 0:
            return 100
        elapsed = (timezone.now() - self.start_date).total_seconds()
        return max(0, min(100, round(elapsed / total * 100)))


class JobRequest(models.Model):
    """A request to build something: postable to the pool, or assigned directly to a member."""

    corporation = models.ForeignKey(
        EveCorporationInfo, on_delete=models.CASCADE, related_name="industrypool_job_requests"
    )
    blueprint_type = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="+")
    activity = models.CharField(
        max_length=20, choices=JobActivity.choices, default=JobActivity.MANUFACTURING
    )
    runs = models.PositiveIntegerField(default=1)
    quantity = models.PositiveIntegerField(default=1, help_text="Number of finished items requested")

    hangar_divisions = models.ManyToManyField(
        CorpHangarDivision,
        blank=True,
        related_name="job_requests",
        help_text="Corp hangar division(s) materials should be pulled from",
    )

    status = models.CharField(
        max_length=20, choices=JobRequestStatus.choices, default=JobRequestStatus.OPEN
    )
    priority = models.PositiveSmallIntegerField(default=3, help_text="1 = highest priority")

    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="industrypool_jobs_created"
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="industrypool_jobs_assigned",
    )
    claimed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="industrypool_jobs_claimed",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)

    tracked_job = models.OneToOneField(
        TrackedIndustryJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_request",
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        ordering = ["priority", "created_at"]

    def __str__(self) -> str:
        return f"{self.blueprint_type} x{self.quantity} ({self.get_status_display()})"

    @property
    def is_open(self) -> bool:
        return self.status == JobRequestStatus.OPEN

    @property
    def is_claim_expired(self) -> bool:
        """Whether this job has been claimed but not started building for longer than the corp's timeout."""
        if self.status != JobRequestStatus.CLAIMED or not self.claimed_at:
            return False
        config = getattr(self.corporation, "industrypool_config", None)
        if not config or not config.claim_timeout_hours:
            return False
        return timezone.now() >= self.claimed_at + timedelta(hours=config.claim_timeout_hours)

    @property
    def builder(self):
        """The user actually on the hook to build this: whoever claimed or was assigned."""
        return self.claimed_by or self.assigned_to

    def claim(self, user) -> None:
        self.claimed_by = user
        self.claimed_at = timezone.now()
        self.status = JobRequestStatus.CLAIMED
        self.save(update_fields=["claimed_by", "claimed_at", "status", "updated_at"])

    def assign(self, user) -> None:
        self.assigned_to = user
        self.status = JobRequestStatus.ASSIGNED
        self.save(update_fields=["assigned_to", "status", "updated_at"])

    def release_claim(self) -> None:
        """Return an expired/abandoned claim to the open pool."""
        self.claimed_by = None
        self.claimed_at = None
        self.status = JobRequestStatus.OPEN
        self.save(update_fields=["claimed_by", "claimed_at", "status", "updated_at"])

    def cancel(self) -> None:
        self.status = JobRequestStatus.CANCELLED
        self.save(update_fields=["status", "updated_at"])


class JobRequestMaterial(models.Model):
    """A material required to fulfil a job request."""

    job_request = models.ForeignKey(JobRequest, on_delete=models.CASCADE, related_name="materials")
    eve_type = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="+")
    quantity_required = models.PositiveIntegerField()
    quantity_available = models.PositiveIntegerField(
        default=0, help_text="Last known quantity in the corp hangar"
    )

    class Meta:
        default_permissions = ()
        unique_together = ("job_request", "eve_type")

    def __str__(self) -> str:
        return f"{self.eve_type} x{self.quantity_required}"

    @property
    def is_sufficient(self) -> bool:
        return self.quantity_available >= self.quantity_required


class BlueprintInventory(models.Model):
    """Tracks individual blueprint items in corp hangars.

    Each row represents a single blueprint item (BPO or BPC stack) identified
    by its ESI ``item_id``. This allows multiple BPCs of the same type with
    different ME/TE levels in the same division to be tracked separately.
    """

    corporation = models.ForeignKey(
        TrackedCorporation, on_delete=models.CASCADE, related_name="blueprint_inventory"
    )
    blueprint_type = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="+")
    location_division = models.ForeignKey(
        CorpHangarDivision, on_delete=models.CASCADE, related_name="blueprints"
    )
    item_id = models.PositiveBigIntegerField(
        help_text="Unique ESI item ID for this individual blueprint"
    )
    quantity = models.PositiveIntegerField(
        default=0, help_text="BPO = 1, BPC = runs remaining on this copy"
    )
    material_efficiency = models.PositiveSmallIntegerField(
        default=0, help_text="Material Efficiency level (0-10)"
    )
    time_efficiency = models.PositiveSmallIntegerField(
        default=0, help_text="Time Efficiency level (0-20)"
    )
    is_original = models.BooleanField(
        default=False, help_text="True if this is a Blueprint Original (BPO)"
    )
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        unique_together = ("corporation", "item_id")
        verbose_name = "Blueprint Inventory"
        verbose_name_plural = "Blueprint Inventories"

    def __str__(self) -> str:
        kind = "BPO" if self.is_original else f"BPC({self.quantity}r)"
        return f"{self.blueprint_type} {kind} ME{self.material_efficiency}/TE{self.time_efficiency} @ {self.location_division}"

    @property
    def is_available_for_copying(self) -> bool:
        """Check if this blueprint can be used for copying."""
        return self.is_original and self.quantity > 0

    @property
    def is_available_for_manufacturing(self) -> bool:
        """Check if this blueprint can be used for manufacturing."""
        if self.is_original:
            return True  # BPOs can always manufacture
        return self.quantity > 0  # BPC needs remaining runs


class JobDependency(models.Model):
    """Links copy jobs to manufacturing jobs."""

    DEPENDENCY_TYPES = (
        ("copy_to_manufacture", "Copy to Manufacture"),
        ("copy_to_copy", "Copy to Copy"),
    )

    parent_job = models.ForeignKey(
        JobRequest, on_delete=models.CASCADE, related_name="dependencies"
    )
    child_job = models.ForeignKey(
        JobRequest, on_delete=models.CASCADE, related_name="dependents"
    )
    dependency_type = models.CharField(
        max_length=20, choices=DEPENDENCY_TYPES, default="copy_to_manufacture"
    )
    required_quantity = models.PositiveIntegerField(
        default=1, help_text="Number of copies required from child job"
    )
    is_satisfied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        unique_together = ("parent_job", "child_job")
        verbose_name = "Job Dependency"
        verbose_name_plural = "Job Dependencies"

    def __str__(self) -> str:
        return f"{self.parent_job} depends on {self.child_job}"


class JobComment(models.Model):
    """A comment / progress update posted on a job request by the builder or managers."""

    job_request = models.ForeignKey(
        JobRequest, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="industrypool_comments"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment by {self.author} on {self.job_request}"


class JobTemplate(models.Model):
    """A reusable template for creating job requests quickly."""

    name = models.CharField(max_length=100)
    corporation = models.ForeignKey(
        EveCorporationInfo, on_delete=models.CASCADE, related_name="industrypool_templates"
    )
    blueprint_type = models.ForeignKey(EveType, on_delete=models.PROTECT, related_name="+")
    activity = models.CharField(
        max_length=20, choices=JobActivity.choices, default=JobActivity.MANUFACTURING
    )
    runs = models.PositiveIntegerField(default=1)
    quantity = models.PositiveIntegerField(default=1)
    hangar_divisions = models.ManyToManyField(
        CorpHangarDivision, blank=True, related_name="templates"
    )
    priority = models.PositiveSmallIntegerField(default=3)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="industrypool_templates_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
