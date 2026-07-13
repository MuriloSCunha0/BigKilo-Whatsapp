from django import forms
from django.contrib import admin
from django.db.models import Sum
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from cardapio.models import DIAS_SEMANA
from config.admin_mixins import LocalizedAdminMixin, LocalizedInlineMixin

from .models import (
    AreaEntrega,
    Cliente,
    ConfiguracaoLoja,
    FLUXO_ETAPAS,
    VARIAVEIS_DESC,
    ChaveMensagem,
    ItemAcompanhamento,
    ItemPedido,
    LogMensagem,
    MensagemCliente,
    Pedido,
    PerfilFluxo,
    PromocaoExclusiva,
    SessaoBot,
    mensagem,
)

_CHAVE_LABEL = dict(ChaveMensagem.choices)


def _moeda(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


# ===================== Configuração da loja (singleton) =====================
class ConfiguracaoLojaForm(forms.ModelForm):
    dias_funcionamento = forms.MultipleChoiceField(
        choices=DIAS_SEMANA, required=False, widget=forms.CheckboxSelectMultiple,
        label=_("Dias de funcionamento"), help_text=_("Nenhum marcado = todos os dias."),
    )

    class Meta:
        model = ConfiguracaoLoja
        exclude = ("mensagem_abertura", "area_atendimento_texto")

    def clean_dias_funcionamento(self):
        return [int(d) for d in self.cleaned_data.get("dias_funcionamento", [])]


@admin.register(ConfiguracaoLoja)
class ConfiguracaoLojaAdmin(LocalizedAdminMixin, ModelAdmin):
    form = ConfiguracaoLojaForm
    readonly_fields = ("link_mensagens",)
    fieldsets = (
        (_("Identidade"), {"fields": ("nome_loja", "slogan")}),
        (_("Mensagens do WhatsApp"), {
            "fields": ("link_mensagens",),
            "description": _("A saudação e os textos do bot ficam em Fluxos de mensagem — não nesta tela."),
        }),
        (_("Preços — Refeição completa"), {
            "fields": (
                ("completa_300", "lim_acomp_300", "lim_prot_300"),
                ("completa_500", "lim_acomp_500", "lim_prot_500"),
                ("completa_700", "lim_acomp_700", "lim_prot_700"),
            ),
            "description": _("Preço do prato montado por tamanho e quantos acompanhamentos/proteínas "
                             "cada tamanho permite. Vale para todas as proteínas."),
        }),
        (_("Preços — Só proteína"), {
            "fields": (
                ("proteina_300", "proteina_500"),
                ("proteina_700", "proteina_1000"),
            ),
            "description": _("Preço padrão da proteína sozinha por tamanho. Uma carne específica pode ter "
                             "preço próprio em Produtos (campo 'Preço por kg')."),
        }),
        (_("Entrega"), {
            "fields": ("taxa_entrega",),
            "description": _("Taxa paga ao entregador — informada ao cliente, não entra no Pix."),
        }),
        (_("Referência (opcional)"), {
            "fields": ("chave_pix",),
            "classes": ("collapse",),
            "description": _("Apenas anotação interna. A cobrança Pix é gerada pelo Asaas automaticamente."),
        }),
        (_("Funcionamento"), {"fields": ("dias_funcionamento", "hora_abertura", "hora_fechamento")}),
    )

    @display(description=_("Editar mensagens do bot"))
    def link_mensagens(self, obj):
        return format_html(
            '<a class="button" style="background:#d97706;color:#fff;border-radius:8px;padding:.45rem .9rem;'
            'text-decoration:none;" href="/admin/pedidos/perfilfluxo/">Abrir Fluxos de mensagem</a> '
            '<span style="color:#6b7280;font-size:.85rem;margin-left:.5rem;">'
            'Edite saudação, área de atendimento, confirmação de pagamento etc.</span>'
        )

    def has_add_permission(self, request):
        return not ConfiguracaoLoja.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Singleton: vai direto para a edição do registro único.
        from django.shortcuts import redirect
        obj = ConfiguracaoLoja.get()
        return redirect("admin:pedidos_configuracaoloja_change", obj.pk)


@admin.register(AreaEntrega)
class AreaEntregaAdmin(ModelAdmin):
    change_list_template = "admin/pedidos/areaentrega/change_list.html"
    list_display = ("bairro", "cep_inicio", "cep_fim", "ativo")
    list_editable = ("ativo",)
    list_filter = ("ativo",)
    search_fields = ("bairro", "cep_inicio", "cep_fim")


class MensagemClienteInline(TabularInline):
    model = MensagemCliente
    extra = 0
    fields = ("chave", "texto")
    verbose_name_plural = "Mensagens personalizadas (sobrescrevem a padrão para este contato)"


class PromocaoExclusivaInline(LocalizedInlineMixin, TabularInline):
    model = PromocaoExclusiva
    extra = 0
    autocomplete_fields = ("produto",)
    fields = ("produto", "desconto_percentual", "mensagem", "data_inicio", "data_fim", "ativo")
    verbose_name_plural = "Promoções exclusivas deste contato"


@admin.register(Cliente)
class ClienteAdmin(ModelAdmin):
    list_display = ("nome_whatsapp", "telefone", "tem_personalizacao", "criado_em")
    search_fields = ("nome_whatsapp", "telefone")
    inlines = [PromocaoExclusivaInline]
    # Nome e telefone vêm do WhatsApp -> somente leitura.
    readonly_fields = ("nome_whatsapp", "telefone", "criado_em", "qtd_pedidos", "total_gasto", "ultimo_pedido", "personalizar_mensagens", "mensagens_efetivas")
    fieldsets = (
        (_("Contato (vem do WhatsApp)"), {
            "fields": (("nome_whatsapp", "telefone"), "criado_em"),
            "description": _("Estes dados são preenchidos automaticamente e não podem ser editados aqui."),
        }),
        (_("Resumo"), {"fields": (("qtd_pedidos", "total_gasto", "ultimo_pedido"),)}),
        (_("Mensagens deste contato"), {
            "fields": ("personalizar_mensagens", "mensagens_efetivas"),
            "description": _("O que o bot fala com ele hoje. Clique em 'Personalizar mensagens' para editar só para este contato (com proteção das variáveis)."),
        }),
    )

    def has_add_permission(self, request):
        # Clientes são criados automaticamente quando chamam no WhatsApp.
        return False

    @display(description=_("Personalizado"), boolean=True)
    def tem_personalizacao(self, obj):
        return obj.mensagens.exists() or obj.promocoes.exists()

    @display(description=_("Pedidos"))
    def qtd_pedidos(self, obj):
        return obj.pedidos.count()

    @display(description=_("Total gasto"))
    def total_gasto(self, obj):
        total = obj.pedidos.filter(status=Pedido.Status.CONCLUIDO).aggregate(t=Sum("valor_total"))["t"]
        return _moeda(total or 0)

    @display(description=_("Último pedido"))
    def ultimo_pedido(self, obj):
        p = obj.pedidos.order_by("-criado_em").first()
        return p.criado_em.strftime("%d/%m/%Y %H:%M") if p else "—"

    @display(description=_("Editar"))
    def personalizar_mensagens(self, obj):
        return format_html(
            '<a class="button" style="background:#d97706;color:#fff;border-radius:8px;padding:.4rem .9rem;'
            'text-decoration:none;" href="/pedidos/contato/{}/mensagens/">✏️ Personalizar mensagens deste contato</a>',
            obj.id,
        )

    @display(description=_("Mensagens efetivas"))
    def mensagens_efetivas(self, obj):
        chip = ('<span style="font-family:monospace;background:#fef3c7;color:#92400e;'
                'border:1px solid #fcd34d;border-radius:5px;padding:0 .3rem;">{}</span>')
        linhas = []
        for chave, _quando in FLUXO_ETAPAS:
            texto = mensagem(chave, obj, bairro="{bairro}")
            safe = escape(texto)
            for tok in VARIAVEIS_DESC:  # realça as variáveis (ex.: {bairro})
                safe = safe.replace(escape(tok), chip.format(escape(tok)))
            linhas.append(
                f"<div style='margin-bottom:.5rem'><b>{escape(_CHAVE_LABEL.get(chave, chave))}:</b><br>"
                f"<span style='white-space:pre-wrap'>{safe}</span></div>"
            )
        return mark_safe("".join(linhas))


@admin.register(SessaoBot)
class SessaoBotAdmin(ModelAdmin):
    change_form_template = "admin/pedidos/sessaobot/change_form.html"
    list_display = ("telefone", "estado_badge", "atualizado_em")
    list_filter = ("estado_atual",)
    search_fields = ("telefone",)
    actions = ("reiniciar_conversa",)
    # Tela somente leitura: o JSON cru não aparece (editar quebraria a conversa).
    readonly_fields = ("telefone", "estado_legivel", "atualizado_em", "historico", "resumo_carrinho", "acoes_conversa")
    fields = ("telefone", "estado_legivel", "atualizado_em", "acoes_conversa", "historico", "resumo_carrinho")

    def has_add_permission(self, request):
        # Conversas são criadas automaticamente pelo bot.
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    @display(description=_("Estado da conversa"), ordering="estado_atual", label={
        "Menu principal": "info",
        "Aguardando pagamento": "warning",
        "No carrinho": "success",
    })
    def estado_badge(self, obj):
        return obj.get_estado_atual_display()

    @display(description=_("Estado da conversa"))
    def estado_legivel(self, obj):
        return obj.get_estado_atual_display()

    @display(description=_("Resumo do pedido em andamento"))
    def resumo_carrinho(self, obj):
        carrinho = obj.carrinho_json or {}
        endereco = carrinho.get("endereco") or {}
        itens = carrinho.get("itens") or []
        partes = []
        bairro = endereco.get("bairro")
        rua = endereco.get("rua") or endereco.get("endereco")
        if bairro or rua:
            local = ", ".join(p for p in (rua, bairro) if p)
            partes.append(f"<div><b>Endereço:</b> {escape(local)}</div>")
        if itens:
            linhas = "".join(
                f"<li>{escape(str(it.get('nome') or it.get('produto') or 'Item'))}"
                + (f" — {escape(str(it.get('peso_g')))}g" if it.get("peso_g") else "")
                + "</li>"
                for it in itens
            )
            partes.append(f"<div><b>Itens no carrinho ({len(itens)}):</b><ul>{linhas}</ul></div>")
        if not partes:
            return mark_safe("<span style='color:#9ca3af'>Nenhum item em andamento. "
                             "Conversa vazia ou recém-iniciada.</span>")
        return mark_safe("".join(partes))

    @display(description=_("Ações"))
    def acoes_conversa(self, obj):
        return format_html(
            '<a class="button" style="background:#d97706;color:#fff;border-radius:8px;padding:.4rem .9rem;'
            'text-decoration:none;" href="/pedidos/sessao/{}/reiniciar/">↺ Reiniciar conversa</a>'
            '<span style="color:#6b7280;font-size:.8rem;margin-left:.5rem;">'
            'Limpa o carrinho; o cliente verá a saudação na próxima mensagem.</span>',
            obj.telefone,
        )

    @display(description=_("Conversa (cliente x bot)"))
    def historico(self, obj):
        logs = list(LogMensagem.objects.filter(telefone=obj.telefone).order_by("-criado_em")[:40])
        if not logs:
            return mark_safe("<span style='color:#9ca3af'>Sem mensagens registradas ainda.</span>")
        logs.reverse()  # mais antigas primeiro
        bolhas = []
        for log in logs:
            cliente = log.direcao == LogMensagem.Direcao.ENTRADA
            cor = "#dcf8c6" if cliente else "#ffffff"
            lado = "right" if cliente else "left"
            quem = "Cliente" if cliente else "Bot"
            quando = log.criado_em.strftime("%d/%m %H:%M")
            bolhas.append(
                f"<div style='display:flex;justify-content:flex-{'end' if cliente else 'start'};margin:.2rem 0'>"
                f"<div style='max-width:75%;background:{cor};color:#111;border:1px solid #e5e7eb;"
                f"border-radius:10px;padding:.4rem .6rem;font-size:.85rem;white-space:pre-wrap'>"
                f"<div style='font-size:.7rem;color:#6b7280;margin-bottom:.1rem'>{quem} · {quando}</div>"
                f"{escape(log.texto)}</div></div>"
            )
        return mark_safe(
            "<div style='background:#ece5dd;border-radius:10px;padding:.6rem;max-height:420px;"
            "overflow-y:auto'>" + "".join(bolhas) + "</div>"
        )

    @admin.action(description=_("Reiniciar conversa (limpa o carrinho)"))
    def reiniciar_conversa(self, request, queryset):
        n = 0
        for sessao in queryset:
            sessao.estado_atual = SessaoBot.Estado.MENU_PRINCIPAL
            sessao.carrinho_json = {}
            sessao.save(update_fields=["estado_atual", "carrinho_json"])
            n += 1
        self.message_user(request, f"{n} conversa(s) reiniciada(s). O cliente verá a saudação no próximo contato.")


# ===================== Pedidos =====================
class ItemAcompanhamentoInline(TabularInline):
    model = ItemAcompanhamento
    extra = 0
    autocomplete_fields = ("produto",)


class ItemPedidoInline(TabularInline):
    model = ItemPedido
    extra = 0
    can_delete = False
    fields = ("modo", "produto", "peso_g", "variacao", "quantidade", "preco_unitario", "acompanhamentos_str", "observacoes", "subtotal_display")
    readonly_fields = fields
    tab = True

    def has_add_permission(self, request, obj=None):
        return False

    @display(description=_("Acompanhamentos"))
    def acompanhamentos_str(self, obj):
        if not obj.pk:
            return "—"
        itens = obj.acompanhamentos.all()
        return ", ".join(a.produto.nome for a in itens) or "—"

    @display(description=_("Subtotal"))
    def subtotal_display(self, obj):
        if not obj.pk:
            return "—"
        return _moeda(obj.subtotal)


@admin.register(Pedido)
class PedidoAdmin(ModelAdmin):
    list_display = ("id", "cliente", "status_badge", "valor_formatado", "bairro", "agendada_badge", "impressa_badge", "criado_em")
    list_filter = ("status", "comanda_impressa", "data_agendada", "criado_em")
    list_filter_submit = True
    search_fields = ("cliente__telefone", "cliente__nome_whatsapp", "asaas_cobranca_id", "bairro")
    # O pedido vem pronto do WhatsApp: o lojista só muda o Status.
    readonly_fields = (
        "cliente", "valor_total", "data_agendada", "endereco_entrega", "bairro", "cep", "taxa_entrega",
        "observacoes", "asaas_cobranca_id", "asaas_pix_copia_cola", "comanda_impressa",
        "impressa_em", "criado_em", "atualizado_em",
    )
    inlines = [ItemPedidoInline]
    list_per_page = 30
    change_list_template = "admin/pedidos/pedido_change_list.html"

    def has_add_permission(self, request):
        # Pedidos entram somente pelo WhatsApp (bot). Nada de cadastro manual.
        return False
    fieldsets = (
        (None, {"fields": ("cliente", "status", "valor_total", "data_agendada")}),
        (_("Entrega"), {"fields": ("endereco_entrega", "bairro", "cep", "taxa_entrega", "observacoes")}),
        (_("Pagamento (Asaas)"), {"fields": ("asaas_cobranca_id", "asaas_pix_copia_cola")}),
        (_("Cozinha"), {"fields": ("comanda_impressa", "impressa_em")}),
        (_("Datas"), {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    @display(description=_("Status"), ordering="status", label={
        "Aguardando pagamento": "warning",
        "Preparando": "info",
        "Concluído": "success",
        "Cancelado": "danger",
    })
    def status_badge(self, obj):
        return obj.get_status_display()

    @display(description=_("Total"), ordering="valor_total")
    def valor_formatado(self, obj):
        return _moeda(obj.valor_total)

    @display(description=_("Comanda"), label={"Impressa": "success", "Pendente": "warning"})
    def impressa_badge(self, obj):
        return "Impressa" if obj.comanda_impressa else "Pendente"

    @display(description=_("Agendada"))
    def agendada_badge(self, obj):
        return f"📅 {obj.data_agendada.strftime('%d/%m/%Y')}" if obj.data_agendada else "Hoje"


@admin.register(PerfilFluxo)
class PerfilFluxoAdmin(ModelAdmin):
    change_list_template = "admin/pedidos/perfilfluxo/change_list.html"
    list_display = ("nome", "ativo", "qtd_mensagens", "acoes")
    list_editable = ("ativo",)
    search_fields = ("nome",)

    @display(description=_("Mensagens"))
    def qtd_mensagens(self, obj):
        return obj.mensagens.count()

    @display(description=_("Ações"))
    def acoes(self, obj):
        return format_html(
            '<a class="button" style="background:#d97706;color:#fff;border-radius:6px;padding:.2rem .6rem;text-decoration:none;" '
            'href="/pedidos/fluxo/{}/editar/">✏️ Editar</a> '
            '<a class="button" style="background:#16a34a;color:#fff;border-radius:6px;padding:.2rem .6rem;text-decoration:none;" '
            'href="/simulador/?perfil={}">🧪 Testar</a>',
            obj.id, obj.id,
        )
