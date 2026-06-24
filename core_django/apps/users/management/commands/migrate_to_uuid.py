import json
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.apps import apps as django_apps

MODEL_MAP = {
    'users.customuser': 'users.CustomUser',
    'notes.notebook': 'notes.Notebook',
    'notes.word': 'notes.Word',
    'notes.pdfexporttask': 'notes.PDFExportTask',
    'notifications.notification': 'notifications.Notification',
    'gamification.userstreak': 'gamification.UserStreak',
    'gamification.dailytarget': 'gamification.DailyTarget',
    'gamification.studyhistory': 'gamification.StudyHistory',
    'gamification.dailyactivity': 'gamification.DailyActivity',
    'subscriptions.subscriptionplan': 'subscriptions.SubscriptionPlan',
    'subscriptions.usersubscription': 'subscriptions.UserSubscription',
    'subscriptions.subscriptionhistory': 'subscriptions.SubscriptionHistory',
    'subscriptions.volumelimitconfig': 'subscriptions.VolumeLimitConfig',
    'assessments.assessmenttask': 'assessments.AssessmentTask',
    'exams.exam': 'exams.Exam',
    'exams.section': 'exams.Section',
    'exams.question': 'exams.Question',
    'exams.option': 'exams.Option',
    'dictionary_zh.zhword': 'dictionary_zh.ZhWord',
    'dictionary_zh.zhexample': 'dictionary_zh.ZhExample',
}

UUID_MODELS = {
    'users.customuser',
    'notes.notebook',
    'notes.word',
    'notes.pdfexporttask',
    'notifications.notification',
    'gamification.userstreak',
    'gamification.dailytarget',
    'gamification.studyhistory',
    'gamification.dailyactivity',
    'subscriptions.subscriptionplan',
    'subscriptions.usersubscription',
    'subscriptions.subscriptionhistory',
    'subscriptions.volumelimitconfig',
    'assessments.assessmenttask',
}

FK_REFERENCES = {
    ('notes.notebook', 'user'): 'users.customuser',
    ('notes.word', 'notebook'): 'notes.notebook',
    ('notes.pdfexporttask', 'user'): 'users.customuser',
    ('notes.pdfexporttask', 'notebook'): 'notes.notebook',
    ('notifications.notification', 'user'): 'users.customuser',
    ('gamification.userstreak', 'user'): 'users.customuser',
    ('gamification.dailytarget', 'user'): 'users.customuser',
    ('gamification.studyhistory', 'user'): 'users.customuser',
    ('gamification.dailyactivity', 'user'): 'users.customuser',
    ('subscriptions.usersubscription', 'user'): 'users.customuser',
    ('subscriptions.subscriptionhistory', 'user'): 'users.customuser',
    ('assessments.assessmenttask', 'user'): 'users.customuser',
    ('admin.logentry', 'user'): 'users.customuser',
}

IMPORT_ORDER = [
    'subscriptions.subscriptionplan',
    'subscriptions.volumelimitconfig',
    'users.customuser',
    'subscriptions.usersubscription',
    'subscriptions.subscriptionhistory',
    'notes.notebook',
    'notes.word',
    'notes.pdfexporttask',
    'notifications.notification',
    'gamification.userstreak',
    'gamification.dailytarget',
    'gamification.studyhistory',
    'gamification.dailyactivity',
    'assessments.assessmenttask',
    'exams.exam',
    'exams.section',
    'exams.question',
    'exams.option',
    'dictionary_zh.zhword',
    'dictionary_zh.zhexample',
]

def get_deterministic_uuid(model_label, old_pk):
    if not old_pk:
        return None
    try:
        uuid.UUID(str(old_pk))
        return str(old_pk)
    except ValueError:
        pass
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"xiaoyue:{model_label}:{old_pk}"))

class Command(BaseCommand):
    help = "Migrate database records from an old integer primary key schema to a new UUID primary key schema using a JSON dump."

    def add_arguments(self, parser):
        parser.add_argument('dump_file', type=str, help="Path to the old JSON dump file.")

    def handle(self, *args, **options):
        # Disconnect signals to prevent default/side-effect objects from being created
        try:
            from django.db.models.signals import post_save, pre_save
            from apps.subscriptions.signals import create_user_subscription, log_subscription_change, sync_volume_limit_to_redis
            from apps.gamification.signals import create_gamification_profiles

            CustomUser = django_apps.get_model('users.CustomUser')
            UserSubscription = django_apps.get_model('subscriptions.UserSubscription')
            VolumeLimitConfig = django_apps.get_model('subscriptions.VolumeLimitConfig')

            post_save.disconnect(create_user_subscription, sender=CustomUser)
            pre_save.disconnect(log_subscription_change, sender=UserSubscription)
            post_save.disconnect(sync_volume_limit_to_redis, sender=VolumeLimitConfig)
            post_save.disconnect(create_gamification_profiles, sender=CustomUser)

            self.stdout.write(self.style.WARNING("Successfully disconnected post_save and pre_save signals for import."))
        except Exception as sig_err:
            self.stdout.write(self.style.ERROR(f"Warning: Could not disconnect some signals: {sig_err}"))

        dump_file_path = options['dump_file']

        self.stdout.write(self.style.WARNING(f"Reading dump file from {dump_file_path}..."))
        try:
            with open(dump_file_path, 'r', encoding='utf-8') as f:
                records = json.load(f)
        except Exception as e:
            raise CommandError(f"Failed to read dump file: {e}")

        # Filter out records we do not support or skip
        supported_records = []
        for r in records:
            model_label = r['model']
            if model_label in MODEL_MAP:
                supported_records.append(r)
            else:
                self.stdout.write(self.style.NOTICE(f"Skipping unsupported model: {model_label}"))

        # Sort records based on IMPORT_ORDER
        def get_order_key(record):
            model_label = record['model']
            try:
                return IMPORT_ORDER.index(model_label)
            except ValueError:
                return len(IMPORT_ORDER)

        supported_records.sort(key=get_order_key)

        self.stdout.write(self.style.WARNING(f"Found {len(supported_records)} records to migrate. Starting transaction..."))

        try:
            with transaction.atomic():
                for idx, record in enumerate(supported_records):
                    model_label = record['model']
                    old_pk = record['pk']
                    fields = record['fields']

                    model_path = MODEL_MAP[model_label]
                    model_class = django_apps.get_model(model_path)

                    # Compute primary key
                    if model_label in UUID_MODELS:
                        pk = get_deterministic_uuid(model_label, old_pk)
                    else:
                        pk = old_pk

                    # Map fields
                    fields_to_set = {}
                    m2m_fields = {}

                    for field_name, field_value in fields.items():
                        field_obj = model_class._meta.get_field(field_name)

                        if field_obj.many_to_many:
                            m2m_fields[field_name] = field_value
                            continue

                        if field_obj.is_relation and not field_obj.many_to_many:
                            # It's a ForeignKey
                            ref_model = FK_REFERENCES.get((model_label, field_name))
                            if ref_model and field_value is not None:
                                mapped_fk = get_deterministic_uuid(ref_model, field_value)
                            else:
                                mapped_fk = field_value
                            fields_to_set[f"{field_name}_id"] = mapped_fk
                        else:
                            fields_to_set[field_name] = field_value

                    # Set primary key
                    fields_to_set['id'] = pk

                    # Save object
                    if model_class.objects.filter(pk=pk).exists():
                        # Update existing record
                        model_class.objects.filter(pk=pk).update(**fields_to_set)
                        instance = model_class.objects.get(pk=pk)
                    else:
                        instance = model_class(**fields_to_set)
                        instance.save(force_insert=True)

                    # Set M2M fields
                    for field_name, val_list in m2m_fields.items():
                        getattr(instance, field_name).set(val_list)

                    if (idx + 1) % 100 == 0 or (idx + 1) == len(supported_records):
                        self.stdout.write(self.style.SUCCESS(f"Migrated {idx + 1}/{len(supported_records)} records..."))

            self.stdout.write(self.style.SUCCESS("Database migration to UUID completed successfully!"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Migration failed: {e}"))
            import traceback
            traceback.print_exc()
            raise CommandError("Transaction rolled back due to error.")
