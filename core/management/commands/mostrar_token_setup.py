from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = "Mostra o token de configuração inicial enquanto o login master não foi criado."

    def handle(self, *args, **opts):
        if User.objects.exists():
            return
        linha = "=" * 62
        self.stdout.write(
            f"\n{linha}\n  PRIMEIRO ACESSO: abra https://{settings.DOMAIN}/setup/\n"
            f"  Token de configuração: {settings.SETUP_TOKEN}\n{linha}\n"
        )
