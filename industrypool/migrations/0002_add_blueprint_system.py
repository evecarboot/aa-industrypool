# Migration for blueprint inventory and dependency system

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("industrypool", "0001_initial"),
    ]

    operations = [
        # Update JobRequest.status choices to include waiting_for_copies
        migrations.AlterField(
            model_name="jobrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("assigned", "Assigned"),
                    ("claimed", "Claimed"),
                    ("in_progress", "In Progress"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("waiting_for_copies", "Waiting for Copies"),
                ],
                default="open",
                max_length=20,
            ),
        ),

        # Create BlueprintInventory model
        migrations.CreateModel(
            name="BlueprintInventory",
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
                ("quantity", models.PositiveIntegerField(
                    default=0,
                    help_text="Number of blueprint copies (BPO = 1, BPC = runs remaining)"
                )),
                ("material_efficiency", models.PositiveSmallIntegerField(
                    default=0,
                    help_text="Material Efficiency level (0-10)"
                )),
                ("time_efficiency", models.PositiveSmallIntegerField(
                    default=0,
                    help_text="Time Efficiency level (0-20)"
                )),
                ("is_original", models.BooleanField(
                    default=False,
                    help_text="True if this is a Blueprint Original (BPO)"
                )),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                (
                    "corporation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blueprint_inventory",
                        to="industrypool.trackedcorporation",
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
                    "location_division",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blueprints",
                        to="industrypool.corphangardivision",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "unique_together": {("corporation", "blueprint_type", "location_division")},
                "verbose_name": "Blueprint Inventory",
                "verbose_name_plural": "Blueprint Inventories",
            },
        ),
        
        # Create JobDependency model
        migrations.CreateModel(
            name="JobDependency",
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
                ("dependency_type", models.CharField(
                    choices=[("copy_to_manufacture", "Copy to Manufacture"), ("copy_to_copy", "Copy to Copy")],
                    default="copy_to_manufacture",
                    max_length=20
                )),
                ("required_quantity", models.PositiveIntegerField(
                    default=1,
                    help_text="Number of copies required from child job"
                )),
                ("is_satisfied", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "parent_job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dependencies",
                        to="industrypool.jobrequest",
                    ),
                ),
                (
                    "child_job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dependents",
                        to="industrypool.jobrequest",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "unique_together": {("parent_job", "child_job")},
                "verbose_name": "Job Dependency",
                "verbose_name_plural": "Job Dependencies",
            },
        ),
    ]