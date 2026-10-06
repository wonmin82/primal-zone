from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("item_entities", "0003_magazine_socket")]
    operations = [
        migrations.CreateModel(name="ItemMigrationLedger", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name="ID")),
            ("migration_version", models.PositiveIntegerField()),
            ("source_kind", models.CharField(max_length=40)),
            ("source_identity", models.PositiveBigIntegerField()),
            ("completed", models.BooleanField(default=False)),
            ("completed_at", models.DateTimeField(null=True)),
            ("source_digest", models.CharField(max_length=64)),
            ("expected_state", models.JSONField(default=dict)),
            ("created_counts", models.JSONField(default=dict)),
            ("warnings", models.JSONField(default=list)),
        ], options={"constraints": [models.UniqueConstraint(fields=("migration_version", "source_kind", "source_identity"), name="item_migration_source_unique")]}),
        migrations.CreateModel(name="ItemRuntime", fields=[
            ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
            ("version", models.PositiveIntegerField(default=0)),
        ], options={"constraints": [models.CheckConstraint(condition=models.Q(id=1), name="item_runtime_singleton")]}),
    ]
