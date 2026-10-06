from django.apps import AppConfig


class SubmissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.submissions'
    verbose_name = 'Multi-Platform Submission Ingestion and Verification'

    def ready(self):
        # Registers the receivers (quest deletion revokes awarded points).
        from . import signals  # noqa: F401
