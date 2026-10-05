"""아이템이 모두 삭제되어도 재사용하지 않을 전역 순번 발급기를 준비한다."""

from django.db import migrations


def initialize_sequence(apps, schema_editor):
    sequence = apps.get_model("item_entities", "ItemSequence")
    sequence.objects.using(schema_editor.connection.alias).get_or_create(
        pk=1, defaults={"last_value": 0}
    )


class Migration(migrations.Migration):
    dependencies = [("item_entities", "0001_initial")]
    operations = [migrations.RunPython(initialize_sequence, migrations.RunPython.noop)]
