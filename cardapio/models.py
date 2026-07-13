from decimal import ROUND_HALF_UP, Decimal
from datetime import time

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

CEM = Decimal("100")
CENTAVO = Decimal("0.01")

# Dias no padrão Python (Monday=0 ... Sunday=6), usado por date.weekday().
DIAS_SEMANA = [
    (0, "Segunda-feira"),
    (1, "Terça-feira"),
    (2, "Quarta-feira"),
    (3, "Quinta-feira"),
    (4, "Sexta-feira"),
    (5, "Sábado"),
    (6, "Domingo"),
]
DIAS_SEMANA_DICT = dict(DIAS_SEMANA)

# Períodos do dia (janelas), conforme a planilha do Big Kilo.
ALMOCO = (time(11, 0), time(15, 0))
JANTAR = (time(15, 0), time(19, 30))
PERIODOS = {"ALMOCO": ALMOCO, "JANTAR": JANTAR}


class PeriodoChoices(models.TextChoices):
    ALMOCO = "ALMOCO", "Almoço"
    JANTAR = "JANTAR", "Jantar"
    CUSTOM = "CUSTOM", "Personalizado"


class Categoria(models.Model):
    class Tipo(models.TextChoices):
        PROTEINA = "PROTEINA", "Proteína"
        ACOMPANHAMENTO = "ACOMPANHAMENTO", "Acompanhamento"
        GRELHADO = "GRELHADO", "Grelhado"
        ESPETINHO = "ESPETINHO", "Espetinho"
        SANDUICHE = "SANDUICHE", "Sanduíche"
        SOPA = "SOPA", "Sopa"
        BEBIDA = "BEBIDA", "Bebida"
        SOBREMESA = "SOBREMESA", "Sobremesa"
        ADICIONAL = "ADICIONAL", "Adicional"
        OUTRO = "OUTRO", "Outro"

    nome = models.CharField("Nome", max_length=80, help_text="ℹ️ Ex.: Proteínas, Bebidas, Sobremesas.")
    tipo = models.CharField(
        "Tipo", max_length=20, choices=Tipo.choices,
        help_text="ℹ️ Define o papel no bot (proteína e acompanhamento entram no prato; os demais são avulsos).",
    )
    ordem = models.PositiveIntegerField(
        "Ordem de exibição", default=0, help_text="ℹ️ Em que ordem aparece no cardápio (0 = primeiro).",
    )
    ativa = models.BooleanField("Ativa", default=True, help_text="ℹ️ Desmarque para esconder o grupo inteiro.")

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class Produto(models.Model):
    class ModoVenda(models.TextChoices):
        MONTAGEM = "MONTAGEM", "Montagem (por peso)"
        FAIXA = "FAIXA", "Faixas de preço"
        UNIDADE = "UNIDADE", "Unidade (preço fixo)"
        ADICIONAL = "ADICIONAL", "Adicional"

    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="produtos", verbose_name="Categoria",
        help_text="ℹ️ A qual grupo do cardápio o item pertence (Proteínas, Acompanhamentos, Bebidas…).",
    )
    nome = models.CharField(
        "Nome", max_length=120, help_text="ℹ️ Nome que o cliente vê no WhatsApp. Ex.: Carne Assada.",
    )
    descricao = models.TextField(
        "Descrição", blank=True,
        help_text="ℹ️ Detalhes/ingredientes mostrados ao cliente quando ele seleciona o item (opcional).",
    )
    modo_venda = models.CharField(
        "Como é vendido", max_length=12, choices=ModoVenda.choices, default=ModoVenda.UNIDADE,
        help_text="ℹ️ Montagem = entra no prato por peso. Faixa = tamanhos com preços. "
                  "Unidade = preço fixo. Adicional = extra (ex.: queijo).",
    )
    preco = models.DecimalField(
        "Preço fixo (R$)", max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="ℹ️ Só para itens vendidos por Unidade/Adicional. Deixe 0 para Montagem ou Faixa.",
    )
    preco_kg = models.DecimalField(
        "Preço por kg — só proteína (R$)", max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="ℹ️ Opcional. Preço por quilo desta carne no modo 'só proteína' (ex.: 159,90). "
                  "Deixe 0 para usar a tabela padrão da loja.",
    )

    ativo = models.BooleanField(
        "Ativo", default=True, help_text="ℹ️ Desmarque para esconder o item do cardápio (ex.: saiu de linha).",
    )
    esgotado = models.BooleanField(
        "Esgotado", default=False,
        help_text="ℹ️ Marque quando acabar — o item some do cardápio na hora. "
                  "Continua esgotado até você desmarcar.",
    )
    sempre_disponivel = models.BooleanField(
        "Sempre disponível", default=False,
        help_text="ℹ️ Marque para itens fixos (carne assada, arroz…): aparecem sempre que a loja está aberta, "
                  "sem precisar de cardápio. Itens que variam ficam em cardápios.",
    )

    # Promoção (desconto percentual com validade) — aplica ao preço fixo.
    desconto_percentual = models.DecimalField(
        "Desconto (%)", max_digits=5, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="ℹ️ Desconto em porcentagem. Ex.: 10 = 10%. Deixe 0 para sem promoção.",
    )
    promo_inicio = models.DateTimeField(
        "Início da promoção", null=True, blank=True, help_text="ℹ️ Opcional. Em branco = começa já.",
    )
    promo_fim = models.DateTimeField(
        "Fim da promoção", null=True, blank=True, help_text="ℹ️ Opcional. Em branco = sem término.",
    )

    ordem_promo = models.PositiveIntegerField(
        "Ordem na Promoção", default=0,
        help_text="ℹ️ Ordem de exibição na lista de promoções (arraste no painel).",
    )

    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ["categoria__ordem", "nome"]

    def __str__(self):
        return self.nome

    # ---- Disponibilidade ----
    @property
    def disponibilidade_label(self) -> str:
        if self.sempre_disponivel:
            return "Sempre (loja aberta)"
        cards = list(self.cardapios.filter(ativo=True))
        if not cards:
            return "Fora de cardápio"
        return "; ".join(c.nome for c in cards)

    def disponivel_em(self, momento=None) -> bool:
        if not self.ativo or self.esgotado:
            return False
        if self.sempre_disponivel:
            return True
        momento = momento or timezone.localtime()
        # Se houver um cardápio exclusivo no ar, só os exclusivos contam.
        exclusivo_ativo = Cardapio.existe_exclusivo_ativo(momento)
        for card in self.cardapios.filter(ativo=True).prefetch_related("agenda"):
            if exclusivo_ativo and not card.exclusivo:
                continue
            if card.ativo_em(momento):
                return True
        return False

    @property
    def disponivel_agora(self) -> bool:
        return self.disponivel_em()

    def preco_proteina_custom(self, peso_g: int):
        if self.preco_kg and self.preco_kg > 0:
            return (self.preco_kg * Decimal(peso_g) / Decimal("1000")).quantize(
                CENTAVO, rounding=ROUND_HALF_UP
            )
        return None

    # ---- Promoção ----
    @property
    def em_promocao(self) -> bool:
        if not self.ativo or self.desconto_percentual <= 0:
            return False
        agora = timezone.now()
        if self.promo_inicio and agora < self.promo_inicio:
            return False
        if self.promo_fim and agora > self.promo_fim:
            return False
        return True

    @property
    def preco_promocional(self) -> Decimal:
        fator = (CEM - self.desconto_percentual) / CEM
        return (self.preco * fator).quantize(CENTAVO, rounding=ROUND_HALF_UP)

    @property
    def preco_atual(self) -> Decimal:
        return self.preco_promocional if self.em_promocao else self.preco


class Cardapio(models.Model):
    """Conjunto de produtos disponível em certos dias/horários.

    - NORMAL: recorrente por dia da semana + horário (agenda).
    - ESPECIAL: vale por uma faixa de datas (ex.: Dia das Mães).
    Se 'exclusivo' estiver ligado, ao ficar no ar ele SUBSTITUI os cardápios
    normais naquele momento (só ele + itens fixos aparecem).
    """

    class Tipo(models.TextChoices):
        NORMAL = "NORMAL", "Normal (semanal)"
        ESPECIAL = "ESPECIAL", "Especial (por data)"

    nome = models.CharField("Nome", max_length=100, help_text="ℹ️ Ex.: Almoço de Quinta, Dia das Mães.")
    tipo = models.CharField(
        "Tipo", max_length=10, choices=Tipo.choices, default=Tipo.NORMAL,
        help_text="ℹ️ Normal = repete por dia da semana. Especial = vale numa data (ex.: feriado).",
    )
    ativo = models.BooleanField("Ativo", default=True, help_text="ℹ️ Desmarque para desativar o cardápio inteiro.")
    exclusivo = models.BooleanField(
        "Exclusivo", default=False,
        help_text="ℹ️ Quando no ar, substitui os cardápios normais (mostra só ele + os itens fixos). "
                  "Ideal para datas comemorativas.",
    )
    data_inicio = models.DateField(
        "Válido de", null=True, blank=True, help_text="ℹ️ Só para Especial. Primeiro dia em que vale.",
    )
    data_fim = models.DateField(
        "Válido até", null=True, blank=True, help_text="ℹ️ Só para Especial. Último dia em que vale.",
    )
    produtos = models.ManyToManyField(
        Produto, related_name="cardapios", blank=True, verbose_name="Produtos",
        help_text="ℹ️ Itens que aparecem quando este cardápio está no ar.",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Cardápio"
        verbose_name_plural = "Cardápios"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def agenda_label(self) -> str:
        if self.tipo == self.Tipo.ESPECIAL:
            ini = self.data_inicio.strftime("%d/%m/%Y") if self.data_inicio else "?"
            fim = self.data_fim.strftime("%d/%m/%Y") if self.data_fim else "?"
            return f"Especial: {ini} a {fim}" + (" · exclusivo" if self.exclusivo else "")
        rows = list(self.agenda.all())
        base = "; ".join(str(r) for r in rows) if rows else "Sem agenda"
        return base + (" · exclusivo" if self.exclusivo else "")

    def ativo_em(self, momento=None) -> bool:
        if not self.ativo:
            return False
        momento = momento or timezone.localtime()
        if self.tipo == self.Tipo.ESPECIAL:
            hoje = momento.date()
            if not self.data_inicio:
                return False
            if hoje < self.data_inicio:
                return False
            if self.data_fim and hoje > self.data_fim:
                return False
            return True
        dia, agora = momento.weekday(), momento.time()
        return any(r.dia_semana == dia and r.hora_inicio <= agora <= r.hora_fim for r in self.agenda.all())

    @classmethod
    def existe_exclusivo_ativo(cls, momento=None) -> bool:
        """True se há algum cardápio exclusivo no ar agora (suprime os normais)."""
        momento = momento or timezone.localtime()
        for c in cls.objects.filter(ativo=True, exclusivo=True).prefetch_related("agenda"):
            if c.ativo_em(momento):
                return True
        return False


class DisponibilidadeCardapio(models.Model):
    """Janela (dia + horário) em que um cardápio fica ativo."""

    cardapio = models.ForeignKey(
        Cardapio, on_delete=models.CASCADE, related_name="agenda", verbose_name="Cardápio"
    )
    dia_semana = models.PositiveSmallIntegerField(
        "Dia da semana", choices=DIAS_SEMANA, help_text="ℹ️ Em que dia este cardápio fica ativo.",
    )
    periodo = models.CharField(
        "Período", max_length=8, choices=PeriodoChoices.choices, default=PeriodoChoices.ALMOCO,
        help_text="ℹ️ Almoço (11–15h) ou Jantar (15–19h30). 'Personalizado' = defina o horário.",
    )
    hora_inicio = models.TimeField(
        "De", null=True, blank=True,
        help_text="ℹ️ Deixe em branco no Almoço/Jantar (preenche sozinho). No 'Personalizado', informe o horário.",
    )
    hora_fim = models.TimeField(
        "Até", null=True, blank=True,
        help_text="ℹ️ Deixe em branco no Almoço/Jantar (preenche sozinho).",
    )

    class Meta:
        verbose_name = "Horário do cardápio"
        verbose_name_plural = "Horários do cardápio"
        ordering = ["dia_semana", "hora_inicio"]

    def save(self, *args, **kwargs):
        # Almoço/Jantar têm janela fixa; preenchemos automaticamente.
        if self.periodo in PERIODOS:
            self.hora_inicio, self.hora_fim = PERIODOS[self.periodo]
        # Personalizado sem horário informado: usa a janela do almoço como padrão seguro.
        elif not self.hora_inicio or not self.hora_fim:
            self.hora_inicio, self.hora_fim = ALMOCO
        super().save(*args, **kwargs)

    def __str__(self):
        dia = DIAS_SEMANA_DICT.get(self.dia_semana, "?")
        return f"{dia} {self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}"


class FaixaPreco(models.Model):
    """Faixa de preço de um produto FAIXA (ex.: 100g/200g/300g; 300ml/500ml)."""

    produto = models.ForeignKey(
        Produto, on_delete=models.CASCADE, related_name="faixas", verbose_name="Produto"
    )
    rotulo = models.CharField(
        "Tamanho", max_length=30, help_text="ℹ️ Tamanho mostrado ao cliente. Ex.: 300g, 500ml.",
    )
    preco = models.DecimalField(
        "Preço (R$)", max_digits=8, decimal_places=2, help_text="ℹ️ Preço deste tamanho.",
    )
    ordem = models.PositiveIntegerField(
        "Ordem", default=0, help_text="ℹ️ Ordem de exibição (0 aparece primeiro).",
    )

    class Meta:
        verbose_name = "Faixa de preço"
        verbose_name_plural = "Faixas de preço"
        ordering = ["produto", "ordem"]

    def __str__(self):
        return f"{self.rotulo} — R$ {self.preco}"


class Promocao(Produto):
    """Proxy: exibe os produtos como seção 'Promoções' no painel."""

    class Meta:
        proxy = True
        verbose_name = "Promoção"
        verbose_name_plural = "Promoções"
        ordering = ["ordem_promo"]
