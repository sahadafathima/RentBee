from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('bookings', '0002_inappnotification_availabilitynotificationrequest')]
    operations = [
        migrations.AddField(
            model_name='inappnotification', name='booking',
            field=models.ForeignKey(blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notifications', to='bookings.booking')),
        migrations.AddField(
            model_name='inappnotification', name='event',
            field=models.CharField(blank=True, default='', max_length=30)),
        migrations.AddConstraint(
            model_name='inappnotification',
            constraint=models.UniqueConstraint(
                fields=('user', 'booking', 'event'), name='unique_booking_notification_event')),
    ]
