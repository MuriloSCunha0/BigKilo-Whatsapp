# Requisitos do Cliente — Restaurante (Reunião 18/06/2026)

Documento derivado da transcrição da reunião com **Maria Carolina Souza** (dona do
restaurante) e **Murilo Santos** (desenvolvedor). Serve de referência para alinhar o
sistema às necessidades reais do negócio.

## 1. Contexto do negócio
- Restaurante de **comida caseira / bufê por quilo** na Barra da Tijuca (RJ).
- Famoso pela **carne assada**; funciona no almoço e ampliou até **20h**.
- Público recorrente: alunos do colégio Santo Agostinho, moradores do condomínio
  Novo Leblon, trabalhadores do shopping Rio Design Barra, idosos.
- Delivery atual baixo (3–4 pedidos/dia via iFood/99). Objetivo: canal próprio no
  WhatsApp, **automatizado, com mensagens pré-definidas (sem IA)**, reduzindo ao
  máximo o trabalho manual de funcionários.

## 2. Regras comerciais
- Preço **refeição completa: R$ 94,90/kg** (R$ 9,49 / 100g).
- Preço **somente proteína: R$ 129,90/kg** (R$ 12,99 / 100g).
- Pesos oferecidos: **400g / 600g / 800g** (e variações).
- **Até 3 acompanhamentos** por refeição.
- Bebidas e sobremesas (pudim, quindim, refrigerante): **preço fixo**, ofertadas ao
  final do pedido (upsell).
- **Taxa de entrega paga diretamente ao entregador** (não entra no Pix).
- **Asaas**: taxa de R$ 0,99 por transação **absorvida pela lojista** (cliente paga o
  valor cheio; a dona recebe valor − 0,99). NÃO repassar ao cliente.
- WhatsApp API oficial: cobrança por **sessão de 24h**; R$ 0,30 por sessão acima de
  1000/mês (improvável no início).

## 3. Cardápio (estrutura real)
**Itens fixos (todo dia, almoço e noite):** carne assada, frango ensopado, bife na
chapa, filé de frango ou de sobrecoxa, sanduíche de carne assada, **sopa do dia**
(varia diariamente, sem dia fixo).

**Iguarias por dia da semana (apenas no almoço, salvo indicação):**
| Dia | Prato |
|-----|-------|
| Segunda | Dobradinha |
| Terça | Isca de fígado |
| Quarta | Lombo suíno |
| Quinta | Língua ao molho madeira (**até 15h**) |
| Sexta | Rabada e bobó de camarão |
| Sábado | Mocotó com feijão branco |

## 4. Fluxo do bot (máquina de estados)
1. Saudação + **informar área de atendimento** de forma sucinta.
2. **Pedir o endereço logo no início** e validar o **raio de atendimento**; recusar se
   fora da área (evitar frustração no fim).
3. Escolher: **refeição completa** ou **somente proteína** (preços distintos).
4. Refeição → escolher **até 3 acompanhamentos** + 1 proteína.
5. Escolher **peso** (400/600/800g) → preço calculado por peso × preço/kg.
6. **Adicionar outro prato?** (loop).
7. Oferecer **bebida/sobremesa** (preço fixo).
8. Fechar pedido → gerar **Pix copia e cola (Asaas)** com o valor exato.
9. Confirmar pagamento (webhook Asaas) → mensagem ao cliente: "pagamento
   confirmado, pedido em preparação, taxa paga ao entregador, já está chegando".
10. **Sem passo manual** de "saiu para entrega" — quanto menos ação do funcionário,
    melhor.

## 5. Automação da cozinha
- Ao confirmar pagamento → status **PREPARANDO** → **impressão automática da
  comanda** na impressora térmica do restaurante (**conectada por cabo** ao
  computador). É o gatilho para o funcionário montar o pedido.

## 6. Gestão automática (sem depender do funcionário ligar/desligar) — ÊNFASE FORTE
- **Disponibilidade por dia da semana e por horário** para cada produto
  (ex.: língua → quinta até 15h; carne assada → todo dia, almoço e noite).
- Status **ativo/inativo** por produto (já previsto).
- **Categorias/tipos** de produto (almoço, sopas, sanduíches, acompanhamentos,
  proteínas, bebidas, sobremesas) — exibidos em blocos no bot.
- **Promoções** com desconto % e validade (início/fim) — já implementado.

## 7. Painel do lojista
- Cadastro de produtos, preços, promoções, categorias, disponibilidade, status.
- **Gestão de pedidos** (pago/não pago, status) com acompanhamento em tempo real.
- **Sessões do bot**: ver conversas travadas (ex.: idoso mandou áudio que o bot não
  entende) e intervir manualmente pelo WhatsApp.
- **Relatórios/dashboard**: gráficos de itens que mais/menos saem no delivery, para
  moldar o cardápio ao longo do tempo.

## 8. Encomendas / datas comemorativas (FASE FUTURA — cliente pediu para depois)
- Aba separada para Natal, Dia das Mães, Dia dos Pais etc.
- Cardápio próprio, fluxo de **retirada no local** com data/horário escolhidos,
  prazos (ex.: encomenda até 2 dias antes). Regras de entrega próprias.

## 9. Fora de código (responsabilidade da cliente / burocracia Meta)
- **Número de telefone novo e dedicado** (telefone usado demora/pode reprovar).
- **CNPJ**, comprovante de endereço da empresa, **Facebook + Instagram** business.
- Criar **conta comercial no Facebook** (dev envia tutorial); Meta valida em 24–48h.

## 10. Comercial
- Prazo de entrega: **30 dias** (gargalo é a burocracia do WhatsApp, não o código).
- **R$ 500/mês por 10 meses**; depois **R$ 300/mês** de manutenção/suporte/ajustes.
- Pagamento até o **dia 5** de cada mês.

---

## Mapa: o que está pronto × o que falta
| # | Requisito | Status |
|---|-----------|--------|
| 1 | Painel admin moderno (Unfold, tom laranja) | ✅ Pronto |
| 2 | Produto: nome, descrição, preço, ativo/inativo | ✅ Pronto |
| 3 | Promoções (% + validade) | ✅ Pronto |
| 4 | Cliente / SessãoBot / Pedido / ItemPedido (base) | ✅ Pronto |
| 5 | Status do pedido (Aguardando → Preparando → Concluído) | ✅ Pronto |
| 6 | **Categorias/tipos de produto** | ✅ Pronto |
| 7 | **Venda por peso + faixas completa/proteína** | ✅ Pronto (300/500/700g) |
| 8 | **Montagem do prato (acompanhamentos, ItemPedido)** | ✅ Pronto |
| 9 | **Disponibilidade por dia da semana + horário** | ✅ Pronto (Cardápios) |
| 10 | **Bebidas/sobremesas (upsell + menu)** | ✅ Pronto |
| 11 | **Endereço de entrega no Pedido + raio de atendimento** | ✅ Pronto (AreaEntrega) |
| 12 | Integração Asaas (Pix copia e cola) + webhook | ✅ Pronto (Fase 2) |
| 13 | Webhook WhatsApp + máquina de estados | ✅ Pronto (Fase 3) |
| 14 | **Impressão automática da comanda (impressora térmica local)** | ✅ Pronto (print_agent.py) |
| 15 | Mensagens configuráveis (Fluxos de mensagem) | ✅ Pronto |
| 16 | **Dashboard de análise (KPIs + ranking do dia)** | ✅ Pronto |
| 17 | Intervenção manual no WhatsApp pelo painel | ❌ Falta |
| 18 | Aba de encomendas / datas comemorativas | 🕒 Futuro (cliente adiou) |

## Pendências conhecidas
- **Credenciais reais** (ASAAS_API_KEY, META_ACCESS_TOKEN/PHONE_NUMBER_ID/VERIFY_TOKEN)
  para testar Pix e WhatsApp ao vivo — hoje validado por simulação.
- **Intervenção manual** em conversas travadas (responder pelo painel).
- **Impressora**: definir `PRINT_MODE` real (windows/escpos) com o modelo da Maria.
- **CPF no Asaas**: bot usa `ASAAS_DEFAULT_CPF_CNPJ` (não coleta CPF do cliente).
- WhatsApp Cloud API: hoje os menus são por número (texto). Pode evoluir para
  botões/listas interativas.
