"""
Registers the recurring Django-Q2 tasks. Idempotent: safe to run on every deploy.

    python manage.py setup_schedules
    python manage.py qcluster   # the worker that actually runs them
"""

from django.core.management.base import BaseCommand
from django_q.models import Schedule

SCHEDULES = [
    {
        'name': 'harvest_all_active_events',
        'func': 'apps.submissions.services.harvest_worker.harvest_all_active_events',
        'minutes': 5,
    },
    {
        'name': 'cleanup_expired_pings',
        'func': 'apps.locations.views.cleanup_expired_pings',
        'minutes': 10,
    },
]


class Command(BaseCommand):
    help = 'Creates or updates the Django-Q2 schedules for harvesting and location ping cleanup.'

    def handle(self, *args, **options):
        for spec in SCHEDULES:
            schedule, created = Schedule.objects.update_or_create(
                name=spec['name'],
                defaults={
                    'func': spec['func'],
                    'schedule_type': Schedule.MINUTES,
                    'minutes': spec['minutes'],
                    'repeats': -1,
                },
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(
                f"{verb} schedule '{schedule.name}': {spec['func']} every {spec['minutes']} min"
            )
