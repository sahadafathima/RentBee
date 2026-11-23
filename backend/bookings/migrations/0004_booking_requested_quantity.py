from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('bookings', '0003_notification_booking_event')]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='requested_quantity',
            field=models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)]),
        ),
    ]
