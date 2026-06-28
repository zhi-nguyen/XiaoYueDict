from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.subscriptions.models import SubscriptionPlan, VolumeLimitConfig

class Command(BaseCommand):
    help = 'Seed default subscription plans and volume limits configuration'

    def handle(self, *args, **options):
        # 1. Seed Subscription Plans
        plans_data = [
            {
                'tier': 'Free',
                'price': Decimal('0.00'),
                'vat': Decimal('0.00'),
                'description': 'Tra cứu từ vựng cơ bản, giới hạn dung lượng tải tệp.'
            },
            {
                'tier': 'Plus',
                'price': Decimal('49000.00'),
                'vat': Decimal('10.00'),
                'description': 'Tăng giới hạn dung lượng tải tệp, cho phép xuất PDF từ sổ tay.'
            },
            {
                'tier': 'Pro',
                'price': Decimal('99000.00'),
                'vat': Decimal('10.00'),
                'description': 'Luyện thi HSK/IELTS, chấm điểm AI luyện nói/viết không giới hạn.'
            },
            {
                'tier': 'Premium',
                'price': Decimal('499000.00'),
                'vat': Decimal('10.00'),
                'description': 'Mở khóa toàn bộ tính năng của gói Pro vĩnh viễn, không gia hạn.'
            },
        ]

        self.stdout.write('Seeding subscription plans...')
        for plan_info in plans_data:
            plan, created = SubscriptionPlan.objects.update_or_create(
                tier=plan_info['tier'],
                defaults={
                    'price': plan_info['price'],
                    'vat': plan_info['vat'],
                    'description': plan_info['description'],
                }
            )
            status = 'created' if created else 'updated'
            self.stdout.write(f"- Plan {plan.tier}: {status}")

        # 2. Seed Volume Limit Configurations
        limits_data = [
            {
                'tier': 'Guest',
                'mb_per_minute': 1,
                'mb_per_hour': 2,
                'mb_per_day': 5,
                'pdf_daily_limit': 1,
                'pdf_word_limit': 5
            },
            {
                'tier': 'Free',
                'mb_per_minute': 1,
                'mb_per_hour': 4,
                'mb_per_day': 10,
                'pdf_daily_limit': 2,
                'pdf_word_limit': 10
            },
            {
                'tier': 'Plus',
                'mb_per_minute': 2,
                'mb_per_hour': 10,
                'mb_per_day': 30,
                'pdf_daily_limit': 10,
                'pdf_word_limit': 50
            },
            {
                'tier': 'Pro',
                'mb_per_minute': 5,
                'mb_per_hour': 30,
                'mb_per_day': 100,
                'pdf_daily_limit': 50,
                'pdf_word_limit': 200
            },
            {
                'tier': 'Premium',
                'mb_per_minute': 5,
                'mb_per_hour': 30,
                'mb_per_day': 100,
                'pdf_daily_limit': 50,
                'pdf_word_limit': 200
            },
        ]

        self.stdout.write('Seeding volume limit configurations...')
        for limit_info in limits_data:
            config, created = VolumeLimitConfig.objects.update_or_create(
                tier=limit_info['tier'],
                defaults={
                    'mb_per_minute': limit_info['mb_per_minute'],
                    'mb_per_hour': limit_info['mb_per_hour'],
                    'mb_per_day': limit_info['mb_per_day'],
                    'pdf_daily_limit': limit_info['pdf_daily_limit'],
                    'pdf_word_limit': limit_info['pdf_word_limit'],
                }
            )
            status = 'created' if created else 'updated'
            self.stdout.write(f"- Config {config.tier}: {status}")

        self.stdout.write(self.style.SUCCESS('Successfully seeded all subscription data.'))
