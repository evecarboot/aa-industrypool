"""Align BlueprintInventory field definitions with model changes.

- Update quantity help text to reflect per-item tracking.
- Ensure item_id field definition matches the model (nullable, matching 0004).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("industrypool", "0004_blueprint_item_tracking"),
    ]

    operations = [
        migrations.AlterField(
            model_name="blueprintinventory",
            name="quantity",
            field=models.PositiveIntegerField(
                default=0,
                help_text="BPO = 1, BPC = runs remaining on this copy",
            ),
        ),
    ]
