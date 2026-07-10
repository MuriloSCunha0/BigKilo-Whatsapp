
from django.core.management.base import BaseCommand

from pedidos.models import FLUXO_ETAPAS, MENSAGENS_PADRAO, MensagemFluxo, PerfilFluxo


class Command(BaseCommand):
    help = "Atualiza textos do fluxo ativo com os padrões do sistema (copy nova)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--todos",
            action="store_true",
            help="Atualiza todos os perfis, não só o ativo.",
        )

    def handle(self, *args, **options):
        perfis = PerfilFluxo.objects.all() if options["todos"] else [PerfilFluxo.ativo_atual()]
        perfis = [p for p in perfis if p]
        if not perfis:
            perfil = PerfilFluxo.ensure_perfil_padrao()
            perfis = [perfil]
        atualizados = 0
        for perfil in perfis:
            for chave, _ in FLUXO_ETAPAS:
                texto = MENSAGENS_PADRAO.get(chave, "")
                if not texto:
                    continue
                _, created = MensagemFluxo.objects.update_or_create(
                    perfil=perfil, chave=chave, defaults={"texto": texto},
                )
                if created:
                    atualizados += 1
                else:
                    atualizados += 1
            self.stdout.write(self.style.SUCCESS(f"Perfil '{perfil.nome}' sincronizado."))
        self.stdout.write(self.style.SUCCESS(f"Concluído ({len(perfis)} perfil(is))."))
