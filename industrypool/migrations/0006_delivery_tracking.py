"""Add delivery tracking fields to JobRequest.

- delivery_division: where finished items should be delivered
- built_at: when the builder marked the job as built
- delivered_at: when the system verified delivery
- New statuses: BUILT, DELIVERED
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("industrypool", "0005_alter_blueprintinventory_quantity"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobrequest",
            name="delivery_division",
            field=models.ForeignKey(
                blank=True,
                help_text="Corp hangar division where the finished items should be delivered",
                null=True,
                on_delete=models.SET_NULL,
                related_name="delivered_jobs",
                to="industrypool.corphangardivision",
            ),
        ),
        migrations.AddField(
            model_name="jobrequest",
            name="built_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the builder marked the job as built",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="jobrequest",
            name="delivered_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the system verified delivery",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="jobrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("assigned", "Assigned"),
                    ("claimed", "Claimed"),
                    ("in_progress", "In Progress"),
                    ("built", "Built (Awaiting Delivery)"),
                    ("delivered", "Delivered & Verified"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("waiting_for_copies", "Waiting for Copies"),
                ],
                default="open",
                max_length=20,
            ),
        ),
    ]
