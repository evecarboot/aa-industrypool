"""Migration for job comments, job templates, and builder stats support."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("industrypool", "0002_add_blueprint_system"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("eveuniverse", "__latest__"),
        ("eveonline", "0025_remove_evecharacter_last_updated_and_more"),
    ]

    operations = [
        # Job comments
        migrations.CreateModel(
            name="JobComment",
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
                ("text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="industrypool.jobrequest",
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="industrypool_comments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "ordering": ["created_at"],
            },
        ),

        # Job templates
        migrations.CreateModel(
            name="JobTemplate",
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
                ("name", models.CharField(max_length=100)),
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
                ("quantity", models.PositiveIntegerField(default=1)),
                ("priority", models.PositiveSmallIntegerField(default=3)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "corporation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="industrypool_templates",
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
                        related_name="industrypool_templates_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="jobtemplate",
            name="hangar_divisions",
            field=models.ManyToManyField(
                blank=True,
                related_name="templates",
                to="industrypool.corphangardivision",
            ),
        ),
    ]
