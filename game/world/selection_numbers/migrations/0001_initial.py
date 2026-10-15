import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="NumberScope", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("scope_id", models.CharField(max_length=180)),
            ("group_id", models.CharField(max_length=180)),
            ("next_number", models.PositiveBigIntegerField(default=1)),
        ], options={"constraints": [
            models.UniqueConstraint(fields=("scope_id", "group_id"), name="b1_scope_group_unique"),
            models.CheckConstraint(condition=models.Q(next_number__gte=1), name="b1_counter_positive"),
        ]}),
        migrations.CreateModel(name="SelectionNumber", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("kind", models.CharField(max_length=20)),
            ("identity", models.CharField(max_length=100)),
            ("number", models.PositiveBigIntegerField()),
            ("name", models.CharField(max_length=200)),
            ("scope", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="members", to="selection_numbers.numberscope")),
        ], options={"constraints": [
            models.UniqueConstraint(fields=("kind", "identity"), name="b1_object_unique"),
            models.UniqueConstraint(fields=("scope", "number"), name="b1_number_unique"),
            models.CheckConstraint(condition=models.Q(number__gte=1), name="b1_number_positive"),
        ]}),
    ]
