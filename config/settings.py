"""
Configurações do projeto Restaurante (Django 5 / ASGI).

As credenciais sensíveis são lidas de variáveis de ambiente (.env).
Copie .env.example para .env e preencha os valores.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega o .env da raiz do projeto, se existir.
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# ==== Segurança ====
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()
]

# Webhooks chegam via HTTPS de domínios externos (Meta/Asaas). Em produção,
# adicione aqui a URL pública (ex.: https://seu-dominio.com).
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# O Railway expõe o domínio público nesta variável — libera host e CSRF sozinho.
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if _railway_domain:
    ALLOWED_HOSTS.append(_railway_domain)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_railway_domain}")

# Demos via túnel ngrok: libera qualquer subdomínio do ngrok (host + CSRF) em DEBUG.
# Útil para o cliente testar de fora sem deploy. Remova/ignore em produção.
if DEBUG:
    ALLOWED_HOSTS += [".ngrok-free.app", ".ngrok.app", ".ngrok.io", ".ngrok-free.dev"]
    CSRF_TRUSTED_ORIGINS += [
        "https://*.ngrok-free.app", "https://*.ngrok.app",
        "https://*.ngrok.io", "https://*.ngrok-free.dev",
    ]


SHARED_APPS = [
    "django_tenants",
    "clientes",  # app de tenant
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "adminsortable2",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

TENANT_APPS = [
    # Apps do tenant
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "adminsortable2",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cardapio",
    "pedidos.apps.PedidosConfig",
    "bot",
    "pagamentos",
]

INSTALLED_APPS = list(set(SHARED_APPS + TENANT_APPS))

TENANT_MODEL = "clientes.Cliente"
TENANT_DOMAIN_MODEL = "clientes.Dominio"

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serve os arquivos estáticos em produção (logo após o Security).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Ponto de entrada assíncrono.
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"


# django-tenants requer PostgreSQL.
DATABASE_ROUTERS = (
    "django_tenants.routers.TenantSyncRouter",
)

db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PRIVATE_URL") or os.getenv("DATABASE_PUBLIC_URL")
if db_url:
    db_config = dj_database_url.parse(db_url, conn_max_age=600)
    db_config["ENGINE"] = "django_tenants.postgresql_backend"
    DATABASES = {"default": db_config}
else:
    # Local fallback
    DATABASES = {
        "default": {
            "ENGINE": "django_tenants.postgresql_backend",
            "NAME": os.getenv("POSTGRES_DB", os.getenv("PGDATABASE", "railway")),
            "USER": os.getenv("POSTGRES_USER", os.getenv("PGUSER", "postgres")),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", os.getenv("PGPASSWORD", "postgres")),
            "HOST": os.getenv("POSTGRES_HOST", os.getenv("PGHOST", "127.0.0.1")),
            "PORT": os.getenv("POSTGRES_PORT", os.getenv("PGPORT", "5432")),
        }
    }


# ==== Validação de senha ====
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ==== Internacionalização ====
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_L10N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGES = [("pt-br", "Português (Brasil)")]


# ==== Arquivos estáticos ====
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise: compacta e versiona os estáticos (serve rápido, sem CDN).
# Só em produção (em DEBUG, o manifesto exigiria collectstatic e quebraria o runserver).
_static_backend = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==== Integrações externas (lidas pelos apps bot/pagamentos) ====
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_API_VERSION = os.getenv("META_API_VERSION", "v21.0")
META_FLOW_ACOMPANHAMENTOS_ID = os.getenv("META_FLOW_ACOMPANHAMENTOS_ID", "")
META_PIX_NATIVO = env_bool("META_PIX_NATIVO", False)

ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://sandbox.asaas.com/api/v3")
# Token de validação do webhook do Asaas (header "asaas-access-token").
ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "")
# CPF/CNPJ padrão para criar o cliente no Asaas quando não houver (bot não coleta CPF).
ASAAS_DEFAULT_CPF_CNPJ = os.getenv("ASAAS_DEFAULT_CPF_CNPJ", "")

# Token que o agente de impressão usa para acessar a API (header X-Print-Token).
IMPRESSAO_API_TOKEN = os.getenv("IMPRESSAO_API_TOKEN", "")

# ==== Modo de simulação (testes sem credenciais reais) ====
# Quando True: Asaas gera um Pix fake e o WhatsApp apenas registra no log (não envia).
# Defina MODO_SIMULACAO=False no .env quando tiver as credenciais reais.
MODO_SIMULACAO = env_bool("MODO_SIMULACAO", True)


# ==== Tema do Admin (django-unfold) ====
# Identidade visual do painel do lojista: tom âmbar/laranja (apetite),
# sidebar com ícones (Material Symbols) e seções organizadas.
UNFOLD = {
    "SITE_TITLE": "Big Kilo · Painel",
    "SITE_HEADER": "Big Kilo",
    "SITE_SUBHEADER": "Comida Caseira · Delivery",
    "SITE_SYMBOL": "restaurant",  # ícone Material Symbols ao lado do título
    "DASHBOARD_CALLBACK": "pedidos.dashboard.dashboard_callback",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "THEME": None,  # permite alternância claro/escuro pelo usuário
    "BORDER_RADIUS": "8px",
    "COLORS": {
        "primary": {
            "50": "255 251 235",
            "100": "254 243 199",
            "200": "253 230 138",
            "300": "252 211 77",
            "400": "251 191 36",
            "500": "245 158 11",
            "600": "217 119 6",
            "700": "180 83 9",
            "800": "146 64 14",
            "900": "120 53 15",
            "950": "69 26 3",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Início",
                "separator": True,
                "items": [
                    {"title": "Painel (resumo)", "icon": "dashboard", "link": "/admin/"},
                    {"title": "Pedidos", "icon": "receipt_long", "link": "/admin/pedidos/pedido/"},
                    {"title": "Simulador (testar bot)", "icon": "chat", "link": "/simulador/"},
                ],
            },
            {
                "title": "Cardápio",
                "separator": True,
                "items": [
                    {"title": "Produtos", "icon": "lunch_dining", "link": "/admin/cardapio/produto/"},
                    {"title": "Cardápios", "icon": "menu_book", "link": "/admin/cardapio/cardapio/"},
                    {"title": "Categorias", "icon": "category", "link": "/admin/cardapio/categoria/"},
                    {"title": "Promoções", "icon": "local_offer", "link": "/admin/cardapio/promocao/"},
                ],
            },
            {
                "title": "Configuração da loja",
                "separator": True,
                "items": [
                    {"title": "Dados da loja", "icon": "storefront", "link": "/admin/pedidos/configuracaoloja/"},
                    {"title": "Fluxos de mensagem", "icon": "chat_bubble", "link": "/admin/pedidos/perfilfluxo/"},
                    {"title": "Áreas de entrega", "icon": "map", "link": "/admin/pedidos/areaentrega/"},
                ],
            },
            {
                "title": "Clientes e conversas",
                "separator": True,
                "items": [
                    {"title": "Clientes", "icon": "group", "link": "/admin/pedidos/cliente/"},
                    {"title": "Conversas (WhatsApp)", "icon": "forum", "link": "/admin/pedidos/sessaobot/"},
                ],
            },
            {
                "title": "Avançado",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Usuários do painel", "icon": "manage_accounts", "link": "/admin/auth/user/"},
                    {"title": "Grupos", "icon": "groups", "link": "/admin/auth/group/"},
                ],
            },
        ],
    },
}
