"""Migration to track individual blueprint items by ESI item_id."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("industrypool", "0003_comments_templates_and_more"),
    ]

    operations = [
        # Add item_id field (nullable first so existing rows don't break)
        migrations.AddField(
            model_name="blueprintinventory",
            name="item_id",
            field=models.PositiveBigIntegerField(
                null=True,
                blank=True,
                help_text="Unique ESI item ID for this individual blueprint",
            ),
        ),
        # Remove old unique_together that was (corporation, blueprint_type, location_division)
        migrations.AlterUniqueTogether(
            name="blueprintinventory",
            unique_together=set(),
        ),
        # Add new unique_together on (corporation, item_id)
        migrations.AlterUniqueTogether(
            name="blueprintinventory",
            unique_together={("corporation", "item_id")},
        ),
        # Make item_id non-null after unique_together is set
        # Note: if you have existing BlueprintInventory rows from the old aggregation
        # model, they will have item_id=NULL. You should either delete them and re-sync
        # from ESI, or manually assign unique item_id values before running this migration.
        # For safety we leave it nullable - the sync task will always populate it.
    ]
