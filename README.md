# Autoatendimento WhatsApp — Restaurante

Sistema de autoatendimento via WhatsApp (Meta Cloud API) com pagamento Pix (Asaas),
construído 100% em Django 5 (ASGI), usando o Django Admin como painel do lojista.

## Stack
- Django 5.x (ASGI / views assíncronas)
- PostgreSQL (driver `psycopg` 3)
- `httpx` (cliente HTTP assíncrono)
- Asaas API (Pix) · Meta Cloud API (WhatsApp)

## Apps
| App | Responsabilidade |
|-----|------------------|
| `cardapio` | Cadastro de produtos (Django Admin) |
| `pedidos` | Cliente, SessaoBot, Pedido, ItemPedido + painel de pedidos com auto-refresh |
| `bot` | Webhook do WhatsApp e máquina de estados (Fase 3) |
| `pagamentos` | Integração Asaas e webhook de pagamento (Fase 2) |

## Setup

```bash
# 1. Ambiente virtual
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell

# 2. Dependências
pip install -r requirements.txt

# 3. Variáveis de ambiente
copy .env.example .env

# 4. Banco de dados
python manage.py migrate

# 5. (Recomendado) Dados demo do Big Kilo — cardápio, bairros, fluxo ativo
python seed_demo.py

# 6. Superusuário do painel
python manage.py createsuperuser

# 7. Rodar em ASGI
uvicorn config.asgi:application --reload --host 127.0.0.1 --port 8000
# Painel: http://127.0.0.1:8000/admin/
# Simulador: http://127.0.0.1:8000/simulador/
```

## Deploy no Railway (produção)
O projeto já está pronto para o Railway (Procfile, WhiteNoise, `DATABASE_URL`).

1. Suba o código para um repositório Git (GitHub).
2. No Railway: **New Project → Deploy from GitHub** (aponte para o repo).
3. Adicione o banco: **New → Database → PostgreSQL** (o Railway cria a `DATABASE_URL` e injeta no app).
4. Em **Variables** do serviço web, defina:
   - `DJANGO_SECRET_KEY` = uma chave longa e aleatória
   - `DJANGO_DEBUG` = `False`
   - `MODO_SIMULACAO` = `True` (mude para `False` quando tiver as credenciais reais)
   - (quando tiver) `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, `META_ACCESS_TOKEN`,
     `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN`
5. Deploy. O Procfile roda `migrate` + `collectstatic` + `compilemessages` + `uvicorn`.
6. Crie o admin (aba **Shell/Console** do serviço, ou localmente apontando para a base):
   `python manage.py createsuperuser`
7. Configure os webhooks com o domínio do Railway:
   - Asaas → `https://SEU-APP.up.railway.app/webhook/asaas/`
   - Meta (WhatsApp) → `https://SEU-APP.up.railway.app/webhook/whatsapp/`

O domínio do Railway é liberado automaticamente (host + CSRF) via `RAILWAY_PUBLIC_DOMAIN`.

> **Agente de impressão**: roda no PC do restaurante (`python print_agent.py`).
> Não acessa o banco — usa uma **API com token**. Defina `IMPRESSAO_API_TOKEN`
> no servidor e, no PC, rode com `PRINT_API_URL` + `PRINT_API_TOKEN` (mesmo valor)
> e `PRINT_MODE` (file/windows/escpos).

## Status do desenvolvimento
- [x] **Fase 1** — Modelos de dados + painel do lojista (cardápio e pedidos)
- [x] **Fase 2** — Integração Asaas (cobrança Pix) + webhook `/webhook/asaas/`
- [x] **Fase 3** — Webhook WhatsApp `/webhook/whatsapp/` + máquina de estados
- [x] **Deploy** — pronto para Railway (Procfile, WhiteNoise, PostgreSQL via `DATABASE_URL`)
