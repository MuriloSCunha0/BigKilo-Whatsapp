"""
Configuração ASGI do projeto Restaurante.

Expõe o callable ASGI como a variável de módulo `application`.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
