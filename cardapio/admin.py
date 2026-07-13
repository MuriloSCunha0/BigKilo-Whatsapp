from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from config.admin_mixins import LocalizedAdminMixin, LocalizedInlineMixin
from adminsortable2.admin import SortableAdminMixin

from .models import (
    Cardapio,
    Categoria,
    DisponibilidadeCardapio,
    FaixaPreco,
    Produto,
    Promocao,
)


def _moeda(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


@admin.register(Categoria)
class CategoriaAdmin(ModelAdmin):
    change_list_template = "admin/cardapio/categoria/change_list.html"
    list_display = ("nome", "tipo", "ordem", "ativa", "assistente_link")
    list_editable = ("ativa",)
    list_filter = ("tipo", "ativa")
    search_fields = ("nome",)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["categoria_tipos"] = Categoria.Tipo.choices
        return super().changelist_view(request, extra_context=extra_context)

    @display(description=_("Editar"))
    def assistente_link(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<a href="#" onclick="event.preventDefault();event.stopPropagation();'
            'window.czOpenEdit&&window.czOpenEdit({});" '
            'style="color:#b45309;font-weight:600;">✏️ Editar</a>',
            obj.id,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        url = reverse("admin:cardapio_categoria_changelist") + f"?assistente={object_id}"
        return redirect(url)


class FaixaPrecoInline(LocalizedInlineMixin, TabularInline):
    model = FaixaPreco
    extra = 0
    # "Ordem" é detalhe técnico: fica oculto e segue a ordem de cadastro.
    fields = ("rotulo", "preco")


@admin.register(Produto)
class ProdutoAdmin(LocalizedAdminMixin, ModelAdmin):
    change_list_template = "admin/cardapio/produto/change_list.html"
    list_display = ("nome", "categoria", "modo_venda", "preco_display", "disponibilidade", "disponivel_badge", "esgotado", "ativo", "assistente_link")
    list_editable = ("esgotado",)
    list_filter = ("categoria", "modo_venda", "ativo", "esgotado", "sempre_disponivel")
    list_filter_submit = True
    search_fields = ("nome", "descricao")
    list_per_page = 80
    autocomplete_fields = ("categoria",)
    inlines = [FaixaPrecoInline]
    fieldsets = (
        (_("1. Informações básicas"), {
            "fields": ("categoria", "nome", "descricao", "modo_venda"),
            "description": _("Comece por aqui: a que grupo pertence, o nome e como o item é vendido."),
        }),
        (_("2. Preço"), {
            "fields": ("preco", "preco_kg"),
            "description": _("'Unidade/Adicional' usa o preço fixo; 'Faixa' usa os tamanhos abaixo; "
                             "'Montagem' usa a tabela da loja. Preço/kg só para carne em 'só proteína'."),
        }),
        (_("3. Situação e disponibilidade"), {
            "fields": ("ativo", "esgotado", "sempre_disponivel"),
            "description": _("Marque 'sempre disponível' para os fixos. Itens que variam você adiciona "
                             "em Cardápios (menu lateral)."),
        }),
        (_("Promoção (opcional)"), {
            "fields": ("desconto_percentual", "promo_inicio", "promo_fim"),
            "classes": ("collapse",),
        }),
    )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["wizard_categorias"] = Categoria.objects.filter(ativa=True)
        extra_context["wizard_cardapios"] = Cardapio.objects.filter(ativo=True)
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Avisa quando o item não vai aparecer para ninguém (pegadinha comum):
        # não é "sempre disponível" e não está em nenhum cardápio.
        if obj.ativo and not obj.esgotado and not obj.sempre_disponivel and not obj.cardapios.exists():
            messages.warning(
                request,
                f"Atenção: “{obj.nome}” ainda NÃO vai aparecer para o cliente. "
                "Marque “Sempre disponível” (itens fixos como bebidas e sobremesas) "
                "ou inclua o item em um Cardápio (menu lateral › Cardápios).",
            )

    @display(description=_("Preço"))
    def preco_display(self, obj):
        if obj.modo_venda == Produto.ModoVenda.MONTAGEM:
            return "Por peso (tabela da loja)"
        if obj.modo_venda == Produto.ModoVenda.FAIXA:
            return " / ".join(f"{f.rotulo} {_moeda(f.preco)}" for f in obj.faixas.all()) or "—"
        return _moeda(obj.preco)

    @display(description=_("Disponível em"))
    def disponibilidade(self, obj):
        return obj.disponibilidade_label

    @display(description=_("Agora"), label={"No ar": "success", "Fora": "warning"})
    def disponivel_badge(self, obj):
        return "No ar" if obj.disponivel_agora else "Fora"

    @display(description=_("Editar"))
    def assistente_link(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<a href="#" onclick="event.preventDefault();event.stopPropagation();'
            'window.wzOpenEdit&&window.wzOpenEdit({});" '
            'style="color:#b45309;font-weight:600;">✏️ Editar</a>',
            obj.id,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        url = reverse("admin:cardapio_produto_changelist") + f"?assistente={object_id}"
        return redirect(url)


class DisponibilidadeCardapioInline(TabularInline):
    model = DisponibilidadeCardapio
    extra = 1
    fields = ("dia_semana", "periodo", "hora_inicio", "hora_fim")


@admin.register(Cardapio)
class CardapioAdmin(ModelAdmin):
    change_list_template = "admin/cardapio/cardapio/change_list.html"
    list_display = ("nome", "tipo", "exclusivo", "ativo", "agenda_resumo", "qtd_produtos", "assistente_link")
    list_filter = ("tipo", "ativo", "exclusivo")
    search_fields = ("nome",)
    filter_horizontal = ("produtos",)
    inlines = [DisponibilidadeCardapioInline]

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        grupos = []
        for cat in Categoria.objects.filter(ativa=True).prefetch_related("produtos"):
            prods = list(cat.produtos.all())
            if prods:
                grupos.append((cat.nome, prods))
        extra_context["wizard_produtos_por_cat"] = grupos
        return super().changelist_view(request, extra_context=extra_context)
    fieldsets = (
        (None, {
            "fields": ("nome", "tipo", "ativo", "exclusivo", "produtos"),
            "description": _("Dê um nome, escolha o tipo e os produtos. 'Exclusivo' faz este cardápio "
                             "substituir os normais quando estiver no ar. Itens fixos não precisam de cardápio."),
        }),
        (_("Especial (por data)"), {
            "fields": ("data_inicio", "data_fim"),
            "description": _("Preencha só quando o tipo for 'Especial' (ex.: Dia das Mães). "
                             "Para 'Normal', use os dias/horários abaixo."),
        }),
    )

    @display(description=_("Dias/horários"))
    def agenda_resumo(self, obj):
        return obj.agenda_label

    @display(description=_("Itens"))
    def qtd_produtos(self, obj):
        return obj.produtos.count()

    @display(description=_("Editar"))
    def assistente_link(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<a href="#" onclick="event.preventDefault();event.stopPropagation();'
            'window.cwOpenEdit&&window.cwOpenEdit({});" '
            'style="color:#b45309;font-weight:600;">✏️ Editar</a>',
            obj.id,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        url = reverse("admin:cardapio_cardapio_changelist") + f"?assistente={object_id}"
        return redirect(url)


@admin.register(Promocao)
class PromocaoAdmin(SortableAdminMixin, LocalizedAdminMixin, ModelAdmin):
    change_list_template = "admin/cardapio/promocao/change_list.html"
    list_display = ("nome", "categoria", "preco_de", "desconto_percentual", "preco_por", "vigencia", "status_badge", "assistente_link")
    search_fields = ("nome",)
    list_filter = ("categoria",)
    fields = ("nome", "categoria", "preco", "desconto_percentual", "promo_inicio", "promo_fim")
    readonly_fields = ("nome", "categoria", "preco")

    def has_add_permission(self, request):
        # Promoção não cria produto novo: o "+" abre um modal que aplica desconto
        # a um produto EXISTENTE (o add nativo criaria um Produto sem categoria e quebraria).
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(desconto_percentual__gt=0)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        grupos = []
        for cat in Categoria.objects.filter(ativa=True).prefetch_related("produtos"):
            prods = list(cat.produtos.all())
            if prods:
                grupos.append((cat.nome, prods))
        extra_context["wizard_produtos_por_cat"] = grupos
        return super().changelist_view(request, extra_context=extra_context)

    @display(description=_("De"))
    def preco_de(self, obj):
        return _moeda(obj.preco)

    @display(description=_("Por"))
    def preco_por(self, obj):
        return _moeda(obj.preco_promocional)

    @display(description=_("Validade"))
    def vigencia(self, obj):
        ini = obj.promo_inicio.strftime("%d/%m %H:%M") if obj.promo_inicio else "já"
        fim = obj.promo_fim.strftime("%d/%m %H:%M") if obj.promo_fim else "sem fim"
        return f"{ini} → {fim}"

    @display(description=_("Status"), label={"Ativa": "success", "Agendada/Expirada": "warning", "Inativa": "danger"})
    def status_badge(self, obj):
        if obj.em_promocao:
            return "Ativa"
        if not obj.ativo:
            return "Inativa"
        return "Agendada/Expirada"

    @display(description=_("Editar"))
    def assistente_link(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<a href="#" onclick="event.preventDefault();event.stopPropagation();'
            'window.pmOpenEdit&&window.pmOpenEdit({});" '
            'style="color:#b45309;font-weight:600;">✏️ Editar</a>',
            obj.id,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        url = reverse("admin:cardapio_promocao_changelist") + f"?assistente={object_id}"
        return redirect(url)
