"""
Runs one harvest for an event and prints the stats as JSON.

    python manage.py harvest_event 1
    python manage.py harvest_event 1 --dry-run   # fetch everything, write nothing
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.submissions.services.harvest_worker import harvest_event_submissions


class Command(BaseCommand):
    help = 'Harvests external contributions for one event and prints the stats as JSON.'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=int)
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Perform all fetches but create or update no submissions; list what would be written.',
        )

    def handle(self, *args, **options):
        stats = harvest_event_submissions(options['event_id'], dry_run=options['dry_run'])
        self.stdout.write(json.dumps(stats, indent=2, default=str))
        if not stats.get('found'):
            raise CommandError(f"Event {options['event_id']} not found or inactive.")
