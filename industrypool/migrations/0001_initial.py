# Generated migration for aa-industrypool

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("eveuniverse", "__latest__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("eveonline", "0025_remove_evecharacter_last_updated_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="General",
            fields=[],
            options={
                "managed": False,
                "default_permissions": (),
                "permissions": (
                    ("basic_access", "Can access the Industry Pool app"),
                    ("manage_pool", "Can create, assign and cancel job requests"),
                    ("claim_jobs", "Can claim open job requests from the pool"),
                    ("view_all_jobs", "Can view all job requests and industry jobs across the corporation"),
                ),
            },
        ),
        migrations.CreateModel(
            name="TrackedCorporation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "claim_timeout_hours",
                    models.PositiveIntegerField(
                        default=24,
                        help_text=(
                            "Hours a member has to start building after claiming a job before it's "
                            "automatically returned to the open pool. Set to 0 to disable."
                        ),
                    ),
                ),
                (
                    "corporation",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="industrypool_config",
                        to="eveonline.evecorporationinfo",
                    ),
                ),
                (
                    "director_character",
                    models.ForeignKey(
                        blank=True,
                        help_text="Character with a director-level ESI token used to pull corp industry jobs",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="eveonline.evecharacter",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "verbose_name": "Tracked Corporation",
                "verbose_name_plural": "Tracked Corporations",
            },
        ),
        migrations.CreateModel(
            name="TrackedIndustryJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("job_id", models.PositiveBigIntegerField(unique=True)),
                ("activity_id", models.PositiveSmallIntegerField()),
                ("runs", models.PositiveIntegerField()),
                ("start_date", models.DateTimeField()),
                ("end_date", models.DateTimeField()),
                ("pause_date", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(default="active", max_length=20)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                (
                    "installer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="industrypool_jobs",
                        to="eveonline.evecharacter",
                    ),
                ),
                (
                    "corporation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="industrypool_tracked_jobs",
                        to="eveonline.evecorporationinfo",
                    ),
                ),
                (
                    "blueprint_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="eveuniverse.evetype",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "ordering": ["-start_date"],
            },
        ),
        migrations.CreateModel(
            name="JobRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "activity",
                    models.CharField(
                        choices=[
                            ("manufacturing", "Manufacturing"),
                            ("reaction", "Reaction"),
                            ("invention", "Invention"),
                            ("research_me", "Material Efficiency Research"),
                            ("research_te", "Time Efficiency Research"),
                            ("copying", "Copying"),
                        ],
                        default="manufacturing",
                        max_length=20,
                    ),
                ),
                ("runs", models.PositiveIntegerField(default=1)),
                (
                    "quantity",
                    models.PositiveIntegerField(
                        default=1, help_text="Number of finished items requested"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("assigned", "Assigned"),
                            ("claimed", "Claimed"),
                            ("in_progress", "In Progress"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.PositiveSmallIntegerField(
                        default=3, help_text="1 = highest priority"
                    ),
                ),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "corporation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="industrypool_job_requests",
                        to="eveonline.evecorporationinfo",
                    ),
                ),
                (
                    "blueprint_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="eveuniverse.evetype",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="industrypool_jobs_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="industrypool_jobs_assigned",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "claimed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="industrypool_jobs_claimed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tracked_job",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="job_request",
                        to="industrypool.trackedindustryjob",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "ordering": ["priority", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="CorpHangarDivision",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "division_number",
                    models.PositiveSmallIntegerField(
                        help_text="Corp hangar division, 1-7",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(7),
                        ],
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=100)),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Available for selection on new job requests",
                    ),
                ),
                (
                    "corporation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hangar_divisions",
                        to="industrypool.trackedcorporation",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "unique_together": {("corporation", "division_number")},
                "ordering": ["division_number"],
                "verbose_name": "Corp Hangar Division",
                "verbose_name_plural": "Corp Hangar Divisions",
            },
        ),
        migrations.AddField(
            model_name="jobrequest",
            name="hangar_divisions",
            field=models.ManyToManyField(
                blank=True,
                help_text="Corp hangar division(s) materials should be pulled from",
                related_name="job_requests",
                to="industrypool.corphangardivision",
            ),
        ),
        migrations.CreateModel(
            name="JobRequestMaterial",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity_required",
                    models.PositiveIntegerField(),
                ),
                (
                    "quantity_available",
                    models.PositiveIntegerField(
                        default=0, help_text="Last known quantity in the corp hangar"
                    ),
                ),
                (
                    "job_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="materials",
                        to="industrypool.jobrequest",
                    ),
                ),
                (
                    "eve_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="eveuniverse.evetype",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "unique_together": {("job_request", "eve_type")},
            },
        ),
    ]