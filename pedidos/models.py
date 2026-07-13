from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

CENTAVO = Decimal("0.01")


class ConfiguracaoLoja(models.Model):
    """Configurações gerais da loja (registro único / singleton).

    Centraliza valores que não devem ficar 'chumbados' no código: preços por
    quilo, mensagens do bot, taxa de entrega, horário de funcionamento e Pix.
    """

    nome_loja = models.CharField("Nome da loja", max_length=120, default="Big Kilo")
    slogan = models.CharField("Slogan", max_length=160, default="Comida Caseira")

    # Mensagens do bot
    mensagem_abertura = models.TextField(
        "Mensagem de boas-vindas",
        default=(
            "Olá! Que bom que você entrou em contato com o Big Kilo 🍽️\n"
            "Atendemos a região do Novo Leblon e arredores."
        ),
        help_text="ℹ️ Primeira mensagem que o cliente recebe ao chamar no WhatsApp.",
    )
    area_atendimento_texto = models.CharField(
        "Área de atendimento (resumo)", max_length=200,
        default="Novo Leblon e arredores (Barra da Tijuca)",
        help_text="ℹ️ Frase curta sobre onde vocês entregam. Aparece logo no início da conversa.",
    )

    # Preços da REFEIÇÃO COMPLETA por faixa de peso (acompanhamentos + proteína)
    completa_300 = models.DecimalField("Completa 300g", max_digits=8, decimal_places=2, default=Decimal("31.97"))
    completa_500 = models.DecimalField("Completa 500g", max_digits=8, decimal_places=2, default=Decimal("50.95"))
    completa_700 = models.DecimalField("Completa 700g", max_digits=8, decimal_places=2, default=Decimal("69.93"))
    # Limites de acompanhamentos / proteínas por faixa
    lim_acomp_300 = models.PositiveSmallIntegerField("Máx. acomp. 300g", default=2)
    lim_acomp_500 = models.PositiveSmallIntegerField("Máx. acomp. 500g", default=3)
    lim_acomp_700 = models.PositiveSmallIntegerField("Máx. acomp. 700g", default=4)
    lim_prot_300 = models.PositiveSmallIntegerField("Máx. proteína 300g", default=1)
    lim_prot_500 = models.PositiveSmallIntegerField("Máx. proteína 500g", default=1)
    lim_prot_700 = models.PositiveSmallIntegerField("Máx. proteína 700g", default=2)

    # Preços de SÓ PROTEÍNA por faixa de peso
    proteina_300 = models.DecimalField("Só proteína 300g", max_digits=8, decimal_places=2, default=Decimal("42.47"))
    proteina_500 = models.DecimalField("Só proteína 500g", max_digits=8, decimal_places=2, default=Decimal("68.45"))
    proteina_700 = models.DecimalField("Só proteína 700g", max_digits=8, decimal_places=2, default=Decimal("94.43"))
    proteina_1000 = models.DecimalField("Só proteína 1kg", max_digits=8, decimal_places=2, default=Decimal("133.40"))

    # Entrega e pagamento
    taxa_entrega = models.DecimalField(
        "Taxa de entrega", max_digits=8, decimal_places=2, default=Decimal("7.00"),
        help_text="Uma por pedido. Mostrada ao cliente no fechamento; paga ao entregador na entrega (não entra no Pix).",
    )
    chave_pix = models.CharField(
        "Chave Pix (referência)", max_length=140, blank=True,
        help_text="ℹ️ Opcional — só para sua referência. O Pix do cliente é gerado automaticamente pelo Asaas.",
    )

    # Horário de funcionamento
    hora_abertura = models.TimeField(
        "Abre às", default="11:00", help_text="ℹ️ Fora do horário o bot avisa que está fechado.",
    )
    hora_fechamento = models.TimeField("Fecha às", default="20:00")
    dias_funcionamento = models.JSONField(
        "Dias de funcionamento", default=list, blank=True,
        help_text="Lista de dias (0=Seg ... 6=Dom). Vazio = todos os dias.",
    )

    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Configuração da loja"
        verbose_name_plural = "Configuração da loja"

    def __str__(self):
        return self.nome_loja

    def save(self, *args, **kwargs):
        self.pk = 1  # garante registro único
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def esta_aberta(self) -> bool:
        agora = timezone.localtime()
        if self.dias_funcionamento and agora.weekday() not in self.dias_funcionamento:
            return False
        return self.hora_abertura <= agora.time() <= self.hora_fechamento

    # ---- Tabela de preços por faixa de peso ----
    def preco_completa(self, peso_g: int) -> Decimal:
        return {300: self.completa_300, 500: self.completa_500, 700: self.completa_700}[peso_g]

    def preco_proteina(self, peso_g: int) -> Decimal:
        return {
            300: self.proteina_300, 500: self.proteina_500,
            700: self.proteina_700, 1000: self.proteina_1000,
        }[peso_g]

    def lim_acomp(self, peso_g: int) -> int:
        return {300: self.lim_acomp_300, 500: self.lim_acomp_500, 700: self.lim_acomp_700}[peso_g]

    def lim_prot(self, peso_g: int) -> int:
        return {300: self.lim_prot_300, 500: self.lim_prot_500, 700: self.lim_prot_700}[peso_g]


class AreaEntrega(models.Model):
    """Bairro / faixa de CEP atendido. Usado para validar o raio de entrega."""

    bairro = models.CharField(
        "Bairro", max_length=120,
        help_text="ℹ️ Bairro atendido. O bot só aceita pedidos dos bairros cadastrados aqui.",
    )
    cep_inicio = models.CharField(
        "CEP inicial", max_length=9, blank=True,
        help_text="ℹ️ Opcional. Início da faixa de CEP atendida. Ex.: 22790-000.",
    )
    cep_fim = models.CharField(
        "CEP final", max_length=9, blank=True, help_text="ℹ️ Opcional. Fim da faixa. Ex.: 22799-999.",
    )
    ativo = models.BooleanField("Ativo", default=True, help_text="ℹ️ Desmarque para parar de atender este bairro.")

    class Meta:
        verbose_name = "Área de entrega"
        verbose_name_plural = "Áreas de entrega"
        ordering = ["bairro"]

    def __str__(self):
        return self.bairro

    @staticmethod
    def _cep_num(cep: str) -> int | None:
        digitos = "".join(c for c in (cep or "") if c.isdigit())
        return int(digitos) if digitos else None

    def cobre_cep(self, cep: str) -> bool:
        ini, fim, alvo = self._cep_num(self.cep_inicio), self._cep_num(self.cep_fim), self._cep_num(cep)
        if not (ini and fim and alvo):
            return False
        return ini <= alvo <= fim

    @classmethod
    def atende(cls, bairro: str = "", cep: str = "") -> bool:
        """True se o endereço (bairro ou CEP) está em alguma área ativa."""
        if cep and cls.por_cep(cep):
            return True
        bairro_norm = (bairro or "").strip().lower()
        if bairro_norm:
            return cls.objects.filter(ativo=True, bairro__iexact=bairro_norm).exists()
        return False

    @classmethod
    def por_cep(cls, cep: str):
        """Retorna a primeira área ativa que cobre o CEP, ou None."""
        for area in cls.objects.filter(ativo=True):
            if area.cobre_cep(cep):
                return area
        return None


class Cliente(models.Model):
    telefone = models.CharField(
        "Telefone (WhatsApp)", max_length=20, unique=True,
        help_text="Identificador único no WhatsApp (E.164, ex.: 5521999998888).",
    )
    nome_whatsapp = models.CharField("Nome no WhatsApp", max_length=120, blank=True)
    asaas_cliente_id = models.CharField(
        "ID do cliente (Asaas)", max_length=60, blank=True, db_index=True,
        help_text="Reutilizado para não recriar o cliente a cada cobrança.",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.nome_whatsapp or 'Cliente'} - {self.telefone}"


class SessaoBot(models.Model):
    class Estado(models.TextChoices):
        MENU_PRINCIPAL = "MENU_PRINCIPAL", "Menu principal"
        PEDINDO_ENDERECO = "PEDINDO_ENDERECO", "Pedindo endereço (bairro)"
        PEDINDO_RUA = "PEDINDO_RUA", "Pedindo endereço (rua)"
        PEDINDO_CEP = "PEDINDO_CEP", "Pedindo CEP"
        ESCOLHENDO_PESO = "ESCOLHENDO_PESO", "Escolhendo peso"
        ESCOLHENDO_ITENS = "ESCOLHENDO_ITENS", "Escolhendo proteína"
        MONTANDO_PRATO = "MONTANDO_PRATO", "Montando prato"
        ESCOLHENDO_FIXO = "ESCOLHENDO_FIXO", "Escolhendo item"
        ESCOLHENDO_FAIXA = "ESCOLHENDO_FAIXA", "Escolhendo tamanho"
        NO_CARRINHO = "NO_CARRINHO", "No carrinho"
        FINALIZANDO = "FINALIZANDO", "Finalizando"
        AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO", "Aguardando pagamento"
        CONFIRMANDO_ITEM = "CONFIRMANDO_ITEM", "Confirmando item montado"
        OFERTA_BEBIDA = "OFERTA_BEBIDA", "Escolhendo bebida/sobremesa extra"
        PERGUNTANDO_MAIS_ITEM = "PERGUNTANDO_MAIS_ITEM", "Pedir mais itens? (legado)"
        RESUMO_CARRINHO = "RESUMO_CARRINHO", "Resumo do carrinho"
        PERGUNTANDO_ADICIONAR = "PERGUNTANDO_ADICIONAR", "O que adicionar?"
        PEDINDO_ENDERECO_COMPLETO = "PEDINDO_ENDERECO_COMPLETO", "Pedindo endereço completo"
        ENCOMENDA_FUTURA = "ENCOMENDA_FUTURA", "Encomenda futura"

    telefone = models.CharField("Telefone", max_length=20, primary_key=True)
    estado_atual = models.CharField(
        "Estado atual", max_length=30, choices=Estado.choices, default=Estado.MENU_PRINCIPAL
    )
    carrinho_json = models.JSONField("Carrinho (JSON)", default=dict, blank=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Conversa (WhatsApp)"
        verbose_name_plural = "Conversas (WhatsApp)"

    def __str__(self):
        return f"{self.telefone} [{self.get_estado_atual_display()}]"


class LogMensagem(models.Model):
    """Histórico do bate-papo (cliente x bot), para o lojista acompanhar a conversa."""

    class Direcao(models.TextChoices):
        ENTRADA = "IN", "Cliente"
        SAIDA = "OUT", "Bot"

    telefone = models.CharField("Telefone", max_length=20, db_index=True)
    direcao = models.CharField("De quem", max_length=3, choices=Direcao.choices)
    texto = models.TextField("Mensagem")
    criado_em = models.DateTimeField("Quando", auto_now_add=True)

    class Meta:
        verbose_name = "Mensagem da conversa"
        verbose_name_plural = "Mensagens da conversa"
        ordering = ["criado_em"]

    def __str__(self):
        return f"{self.telefone} {self.get_direcao_display()}: {self.texto[:40]}"


class Pedido(models.Model):
    class Status(models.TextChoices):
        AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO", "Aguardando pagamento"
        PREPARANDO = "PREPARANDO", "Preparando"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        CANCELADO = "CANCELADO", "Cancelado"

    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="pedidos", verbose_name="Cliente"
    )
    status = models.CharField(
        "Status", max_length=30, choices=Status.choices,
        default=Status.AGUARDANDO_PAGAMENTO, db_index=True,
    )
    valor_total = models.DecimalField(
        "Valor total", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Entrega
    endereco_entrega = models.TextField("Endereço de entrega", blank=True)
    bairro = models.CharField("Bairro", max_length=120, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    taxa_entrega = models.DecimalField(
        "Taxa de entrega", max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="Paga ao entregador na entrega (não incluída no Pix).",
    )
    observacoes = models.TextField("Observações gerais", blank=True)

    # Encomenda agendada para uma data futura (opção 3 do menu). Vazio = pedido para hoje.
    data_agendada = models.DateField(
        "Agendada para", null=True, blank=True,
        help_text="Preenchido quando é uma encomenda para outro dia.",
    )

    # Integração Asaas
    asaas_cobranca_id = models.CharField("ID da cobrança (Asaas)", max_length=60, blank=True, db_index=True)
    asaas_pix_copia_cola = models.TextField("Pix Copia e Cola", blank=True)

    # Impressão automática da comanda
    comanda_impressa = models.BooleanField("Comanda impressa", default=False)
    impressa_em = models.DateTimeField("Impressa em", null=True, blank=True)

    criado_em = models.DateTimeField("Criado em", auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido #{self.pk} - {self.cliente.telefone} - {self.get_status_display()}"

    def recalcular_total(self):
        total = sum((item.subtotal for item in self.itens.all()), Decimal("0.00"))
        self.valor_total = total.quantize(CENTAVO, rounding=ROUND_HALF_UP)
        return self.valor_total


class ItemPedido(models.Model):
    """Um item do pedido. Pode ser um prato montado (por peso) ou um item de
    preço fixo (bebida, sobremesa, sanduíche, sopa)."""

    class Modo(models.TextChoices):
        COMPLETA = "COMPLETA", "Refeição completa"
        PROTEINA = "PROTEINA", "Só proteína"
        FIXO = "FIXO", "Item avulso (preço fixo)"

    pedido = models.ForeignKey(
        Pedido, on_delete=models.CASCADE, related_name="itens", verbose_name="Pedido"
    )
    modo = models.CharField("Modo", max_length=10, choices=Modo.choices, default=Modo.FIXO)
    produto = models.ForeignKey(
        "cardapio.Produto", on_delete=models.PROTECT, related_name="itens_pedido",
        verbose_name="Produto / Proteína",
    )
    peso_g = models.PositiveIntegerField(
        "Peso (g)", null=True, blank=True, help_text="Para pratos por peso (300/500/700/1000g)."
    )
    variacao = models.CharField(
        "Variação", max_length=40, blank=True,
        help_text="Faixa/tamanho escolhido (ex.: 500ml, Pão Brioche).",
    )
    quantidade = models.PositiveIntegerField("Quantidade", default=1)
    preco_unitario = models.DecimalField(
        "Preço unitário", max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="Congelado no momento do pedido (proteína/base, sem adicionais).",
    )
    observacoes = models.CharField(
        "Observações", max_length=200, blank=True, help_text="Ex.: sem cebola, bem passado."
    )

    class Meta:
        verbose_name = "Item do Pedido"
        verbose_name_plural = "Itens do Pedido"

    def __str__(self):
        if self.modo == self.Modo.FIXO:
            extra = f" ({self.variacao})" if self.variacao else ""
            return f"{self.quantidade}x {self.produto.nome}{extra}"
        return f"{self.get_modo_display()} {self.peso_g or '?'}g - {self.produto.nome}"

    @property
    def total_adicionais(self) -> Decimal:
        return sum((a.preco_adicional for a in self.acompanhamentos.all()), Decimal("0.00"))

    @property
    def subtotal(self) -> Decimal:
        base = (self.preco_unitario + self.total_adicionais) * self.quantidade
        return base.quantize(CENTAVO, rounding=ROUND_HALF_UP)


class ItemAcompanhamento(models.Model):
    """Acompanhamento escolhido para um prato montado (até N por item)."""

    item_pedido = models.ForeignKey(
        ItemPedido, on_delete=models.CASCADE, related_name="acompanhamentos", verbose_name="Item"
    )
    produto = models.ForeignKey(
        "cardapio.Produto", on_delete=models.PROTECT, related_name="usado_como_acompanhamento",
        verbose_name="Acompanhamento",
    )
    preco_adicional = models.DecimalField(
        "Adicional", max_digits=8, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = "Acompanhamento"
        verbose_name_plural = "Acompanhamentos"

    def __str__(self):
        return self.produto.nome


# ===================== Mensagens do bot (editáveis) =====================
class ChaveMensagem(models.TextChoices):
    BOAS_VINDAS = "BOAS_VINDAS", "Boas-vindas / saudação"
    AREA_ATENDIMENTO = "AREA_ATENDIMENTO", "Área de atendimento (resumo)"
    PEDIR_BAIRRO = "PEDIR_BAIRRO", "Pedir bairro"
    FORA_AREA = "FORA_AREA", "Fora da área de entrega"
    PEDIR_RUA = "PEDIR_RUA", "Pedir rua/endereço"
    PEDIR_CEP = "PEDIR_CEP", "Pedir CEP"
    CEP_INVALIDO = "CEP_INVALIDO", "CEP fora da área"
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO", "Aguardando pagamento"
    PAGAMENTO_CONFIRMADO = "PAGAMENTO_CONFIRMADO", "Pagamento confirmado"
    ANUNCIO_PROMO = "ANUNCIO_PROMO", "Anúncio de promoção"
    PEDIR_ENDERECO_COMPLETO = "PEDIR_ENDERECO_COMPLETO", "Pedir endereço completo (fechamento)"
    ENCOMENDA_EM_BREVE = "ENCOMENDA_EM_BREVE", "Encomenda futura (em breve)"
    MONTAR_REFEICAO = "MONTAR_REFEICAO", "Início montagem refeição"
    ESCOLHER_PROTEINA = "ESCOLHER_PROTEINA", "Escolher proteína"
    ESCOLHER_ACOMPANHAMENTOS = "ESCOLHER_ACOMPANHAMENTOS", "Escolher acompanhamentos"
    PEDIR_MAIS = "PEDIR_MAIS", "Pedir mais itens?"
    RESUMO_CARRINHO = "RESUMO_CARRINHO", "Resumo do carrinho"
    PERGUNTAR_ADICIONAR = "PERGUNTAR_ADICIONAR", "O que adicionar?"
    PEDIR_DATA_ENCOMENDA = "PEDIR_DATA_ENCOMENDA", "Pedir data da encomenda"
    ENCOMENDA_AGENDADA = "ENCOMENDA_AGENDADA", "Encomenda agendada"
    DATA_INVALIDA = "DATA_INVALIDA", "Data inválida"


# Textos padrão (fallback) caso não haja cadastro no banco. {bairro} é substituído.
MENSAGENS_PADRAO = {
    "BOAS_VINDAS": (
        "Olá! Que bom que você falou com o Big Kilo 🍽️\n"
        "Vamos montar seu pedido com calma — eu te guio passo a passo."
    ),
    "AREA_ATENDIMENTO": "Novo Leblon e arredores (Barra da Tijuca)",
    "PEDIR_BAIRRO": "Para começar, informe seu bairro:",
    "FORA_AREA": "Poxa, infelizmente ainda não entregamos nesse CEP. 😕 Obrigado pelo contato!",
    "PEDIR_RUA": "Ótimo, atendemos {bairro}! Agora envie a *rua, número e complemento*.",
    "PEDIR_CEP": "Para começarmos, informe seu *CEP* (só os números, ex.: 22790000):",
    "CEP_INVALIDO": "Esse CEP não está na nossa área de entrega. Confira e tente de novo.",
    "PEDIR_ENDERECO_COMPLETO": (
        "Quase lá! 🏠\n"
        "Informe seu *endereço completo* para entrega: rua, número, complemento e referência."
    ),
    "ENCOMENDA_EM_BREVE": (
        "Agendar encomenda para outro dia estará disponível em breve! 📅\n"
        "Por enquanto, escolha uma refeição para hoje no menu."
    ),
    "PEDIR_DATA_ENCOMENDA": (
        "Vamos agendar sua encomenda! 📅\n"
        "Para que *dia* você quer? Envie no formato dia/mês (ex.: 25/12)."
    ),
    "DATA_INVALIDA": (
        "Não entendi a data. 😕 Envie no formato dia/mês (ex.: 25/12) — precisa ser uma data futura."
    ),
    "ENCOMENDA_AGENDADA": (
        "Encomenda anotada para *{data}*! 📅\n"
        "Agora monte seu pedido normalmente no menu abaixo."
    ),
    "MONTAR_REFEICAO": "Vamos montar sua refeição! Toque em *Escolher peso* e selecione o tamanho:",
    "ESCOLHER_PROTEINA": "Escolha a *proteína* na lista abaixo:",
    "ESCOLHER_ACOMPANHAMENTOS": (
        "Escolha os acompanhamentos (mínimo 1, máximo {lim}).\n"
        "Toque para marcar as opções e depois confirme."
    ),
    "PEDIR_MAIS": "Quer adicionar *mais alguma coisa* ao pedido?",
    "RESUMO_CARRINHO": "Confira seu pedido abaixo e escolha uma opção:",
    "PERGUNTAR_ADICIONAR": "Quer incluir *bebida*, *sobremesa* ou *outra refeição*?",
    "AGUARDANDO_PAGAMENTO": "Estamos aguardando o pagamento. Para um novo pedido, digite *cancelar*.",
    "PAGAMENTO_CONFIRMADO": (
        "✅ Pagamento confirmado! Seu pedido já está sendo preparado.\n"
        "A taxa de entrega é paga diretamente ao entregador. Já já chega aí! 🍽️"
    ),
    "ANUNCIO_PROMO": "🎁 Temos promoções hoje! Confira no cardápio.",
}


# Ordem do fluxo + "quando aparece" (para a tela de edição interativa).
FLUXO_ETAPAS = [
    ("BOAS_VINDAS", "No início, quando o cliente manda a 1ª mensagem."),
    ("AREA_ATENDIMENTO", "Texto curto da área de entrega, mostrado na saudação."),
    ("PEDIR_CEP", "Logo após a saudação — validação de área."),
    ("FORA_AREA", "Quando o CEP está fora da área de entrega."),
    ("CEP_INVALIDO", "Quando o CEP é inválido ou fora da faixa."),
    ("ANUNCIO_PROMO", "Ao entrar no menu, se houver promoção ativa."),
    ("MONTAR_REFEICAO", "Ao iniciar montagem de refeição completa."),
    ("ESCOLHER_PROTEINA", "Ao escolher proteína."),
    ("ESCOLHER_ACOMPANHAMENTOS", "Ao escolher acompanhamentos."),
    ("PEDIR_ENDERECO_COMPLETO", "Ao fechar o pedido — endereço completo."),
    ("PEDIR_MAIS", "Ao perguntar se quer adicionar mais ao pedido."),
    ("RESUMO_CARRINHO", "Resumo do carrinho após cada item adicionado."),
    ("PERGUNTAR_ADICIONAR", "Ao oferecer bebida, sobremesa ou outra refeição."),
    ("PEDIR_DATA_ENCOMENDA", "Opção 3 — pede a data da encomenda futura."),
    ("ENCOMENDA_AGENDADA", "Depois que o cliente informa a data da encomenda."),
    ("AGUARDANDO_PAGAMENTO", "Enquanto aguarda o pagamento do Pix."),
    ("PAGAMENTO_CONFIRMADO", "Quando o pagamento é confirmado."),
]
# Variáveis obrigatórias por mensagem (não podem ser removidas pelo lojista).
VARIAVEIS_MENSAGEM = {
    "PEDIR_RUA": ["{bairro}"],
    "CEP_INVALIDO": ["{bairro}"],
    "ESCOLHER_ACOMPANHAMENTOS": ["{lim}"],
    "ENCOMENDA_AGENDADA": ["{data}"],
}
# Explicação de cada variável (mostrada na tela de edição).
VARIAVEIS_DESC = {
    "{bairro}": "nome do bairro (ex.: Novo Leblon)",
    "{lim}": "quantidade máxima de acompanhamentos (ex.: 4)",
    "{data}": "data da encomenda (ex.: 25/12)",
}
# Amostras para preview no editor de fluxo.
PREVIEW_AMOSTRAS = {"{bairro}": "Novo Leblon", "{lim}": "4", "{data}": "25/12"}

# Agrupamento visual no editor de fluxo.
FLUXO_GRUPOS = [
    ("começo", "Começo do atendimento", ["BOAS_VINDAS", "AREA_ATENDIMENTO", "PEDIR_CEP", "FORA_AREA", "CEP_INVALIDO", "ANUNCIO_PROMO"]),
    ("cardapio", "Montagem do prato", ["MONTAR_REFEICAO", "ESCOLHER_PROTEINA", "ESCOLHER_ACOMPANHAMENTOS"]),
    ("carrinho", "Carrinho e fechamento", ["RESUMO_CARRINHO", "PERGUNTAR_ADICIONAR", "PEDIR_MAIS", "PEDIR_ENDERECO_COMPLETO"]),
    ("encomenda", "Encomenda futura", ["PEDIR_DATA_ENCOMENDA", "ENCOMENDA_AGENDADA"]),
    ("pagamento", "Pagamento", ["AGUARDANDO_PAGAMENTO", "PAGAMENTO_CONFIRMADO"]),
]


class PerfilFluxo(models.Model):
    """Conjunto de textos do fluxo (um 'tema' de conversa). Ative um por vez,
    como um cardápio. O fluxo (saudação→pedido→pagamento) é sempre o mesmo;
    muda apenas o texto das mensagens."""

    nome = models.CharField("Nome", max_length=100, help_text="ℹ️ Ex.: Padrão, Natal, Tom descontraído.")
    ativo = models.BooleanField("Ativo", default=False, help_text="ℹ️ Só um perfil fica ativo por vez.")
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Fluxo de mensagens"
        verbose_name_plural = "Fluxos de mensagem"
        ordering = ["-ativo", "nome"]

    def __str__(self):
        return self.nome + (" (ativo)" if self.ativo else "")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.ativo:  # garante um único perfil ativo
            PerfilFluxo.objects.exclude(pk=self.pk).filter(ativo=True).update(ativo=False)

    @classmethod
    def ativo_atual(cls):
        return cls.objects.filter(ativo=True).first()

    @classmethod
    def ensure_perfil_padrao(cls):
        """Garante um fluxo ativo com mensagens padrão (instalação zerada)."""
        ativo = cls.objects.filter(ativo=True).first()
        if ativo and ativo.mensagens.exists():
            return ativo
        perfil, _ = cls.objects.get_or_create(nome="Padrão", defaults={"ativo": True})
        for chave, _quando in FLUXO_ETAPAS:
            texto = MENSAGENS_PADRAO.get(chave, "")
            if texto:
                MensagemFluxo.objects.update_or_create(
                    perfil=perfil, chave=chave, defaults={"texto": texto},
                )
        if not perfil.ativo:
            perfil.ativo = True
            perfil.save(update_fields=["ativo"])
        return perfil

    def texto_de(self, chave):
        mf = self.mensagens.filter(chave=chave).first()
        return mf.texto if mf else MENSAGENS_PADRAO.get(chave, "")


class MensagemFluxo(models.Model):
    """Texto de uma etapa dentro de um perfil de fluxo."""

    perfil = models.ForeignKey(
        PerfilFluxo, on_delete=models.CASCADE, related_name="mensagens", verbose_name="Perfil"
    )
    chave = models.CharField("Etapa", max_length=30, choices=ChaveMensagem.choices)
    texto = models.TextField("Texto")

    class Meta:
        verbose_name = "Mensagem do fluxo"
        verbose_name_plural = "Mensagens do fluxo"
        unique_together = ("perfil", "chave")

    def __str__(self):
        return f"{self.perfil.nome} · {self.get_chave_display()}"


class MensagemCliente(models.Model):
    """Sobrescreve uma mensagem só para um contato específico."""

    cliente = models.ForeignKey(
        Cliente, on_delete=models.CASCADE, related_name="mensagens", verbose_name="Cliente"
    )
    chave = models.CharField("Etapa", max_length=30, choices=ChaveMensagem.choices)
    texto = models.TextField("Texto personalizado")

    class Meta:
        verbose_name = "Mensagem personalizada"
        verbose_name_plural = "Mensagens personalizadas"
        unique_together = ("cliente", "chave")

    def __str__(self):
        return f"{self.cliente.telefone} · {self.get_chave_display()}"


class PromocaoExclusiva(models.Model):
    """Promoção vinculada a um contato específico (desconto sobre o preço fixo)."""

    cliente = models.ForeignKey(
        Cliente, on_delete=models.CASCADE, related_name="promocoes", verbose_name="Cliente"
    )
    produto = models.ForeignKey(
        "cardapio.Produto", on_delete=models.CASCADE, related_name="promocoes_exclusivas",
        verbose_name="Produto", help_text="ℹ️ Funciona com itens de preço fixo (bebida, sanduíche, etc.).",
    )
    desconto_percentual = models.DecimalField("Desconto (%)", max_digits=5, decimal_places=2)
    mensagem = models.CharField(
        "Mensagem de anúncio", max_length=200, blank=True,
        help_text="ℹ️ Texto que o bot mostra no início para este contato. Ex.: 'Pra você: 20% no pudim! 🍮'",
    )
    data_inicio = models.DateField("Início", null=True, blank=True)
    data_fim = models.DateField("Fim", null=True, blank=True)
    ativo = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Promoção exclusiva"
        verbose_name_plural = "Promoções exclusivas"

    def __str__(self):
        return f"{self.cliente.telefone} · {self.produto.nome} ({self.desconto_percentual}%)"

    def vigente(self, momento=None) -> bool:
        if not self.ativo:
            return False
        hoje = (momento or timezone.localtime()).date()
        if self.data_inicio and hoje < self.data_inicio:
            return False
        if self.data_fim and hoje > self.data_fim:
            return False
        return True

    @property
    def preco(self):
        fator = (Decimal("100") - self.desconto_percentual) / Decimal("100")
        return (self.produto.preco * fator).quantize(CENTAVO, rounding=ROUND_HALF_UP)


# ===================== Helpers de mensagem e preço por contato =====================
def mensagem(chave: str, cliente=None, perfil=None, **fmt) -> str:
    """Resolve o texto: personalizado do contato -> perfil (preview ou ativo) -> padrão.

    Se `perfil` for passado, usa esse fluxo (modo de teste), em vez do ativo.
    """
    texto = None
    if cliente is not None:
        mc = MensagemCliente.objects.filter(cliente=cliente, chave=chave).first()
        if mc:
            texto = mc.texto
    if texto is None:
        p = perfil or PerfilFluxo.ativo_atual()
        if p:
            mf = p.mensagens.filter(chave=chave).first()
            if mf:
                texto = mf.texto
    if texto is None:
        texto = MENSAGENS_PADRAO.get(chave, "")
    if fmt:
        try:
            return texto.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return texto
    return texto


def promocoes_exclusivas_ativas(cliente, momento=None):
    if not cliente:
        return []
    return [p for p in cliente.promocoes.select_related("produto").all() if p.vigente(momento)]


def preco_para(produto, cliente, momento=None):
    """Preço de um item de preço fixo considerando promoção exclusiva do contato."""
    if cliente:
        pe = next(
            (p for p in promocoes_exclusivas_ativas(cliente, momento) if p.produto_id == produto.id),
            None,
        )
        if pe:
            return pe.preco
    return produto.preco_atual
