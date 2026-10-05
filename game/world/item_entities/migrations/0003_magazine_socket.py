"""magazine socket 한 칸만 제약한다. 다른 socket의 미래 수용량을 제한하지 않는다."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("item_entities", "0002_initialize_sequence")]
    operations = [migrations.AddConstraint(
        model_name="itementity",
        constraint=models.UniqueConstraint(fields=("parent_item", "socket"),
                                           condition=models.Q(socket="magazine"),
                                           name="item_one_magazine_socket"),
    )]
