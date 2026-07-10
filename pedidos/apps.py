from django.apps import AppConfig


class PedidosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pedidos"
    verbose_name = "Pedidos"

    def ready(self):
        # Evita queries antes das migrações (manage.py migrate, etc.).
        from django.db.models.signals import post_migrate

        def _seed_fluxo(sender, **kwargs):
            if sender.name != "pedidos":
                return
            from .models import PerfilFluxo
            try:
                PerfilFluxo.ensure_perfil_padrao()
            except Exception:
                pass

        post_migrate.connect(_seed_fluxo, dispatch_uid="pedidos_seed_fluxo_padrao")
