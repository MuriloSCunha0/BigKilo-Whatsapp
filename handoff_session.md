# Handoff de Sessão: Big Kilo - Integração WhatsApp & Django-Tenants

Este documento contém o estado completo do projeto, credenciais, problemas atuais e próximos passos para que o trabalho possa ser continuado sem perda de contexto em uma nova sessão.

## 1. Visão Geral do Projeto
O projeto é um sistema SaaS de cardápio e pedidos para restaurantes com integração de bot via WhatsApp, utilizando a API oficial (Cloud API do Facebook).
Recentemente, a arquitetura foi migrada para **Multi-Tenant** (usando `django-tenants`), permitindo que múltiplos clientes (restaurantes) utilizem o mesmo banco de dados isoladamente por esquemas (schemas) do PostgreSQL. O nosso primeiro e principal cliente cadastrado no banco de produção é o **Big Kilo**.

## 2. Infraestrutura Atual
- **Hospedagem:** [Railway](https://railway.app/)
- **Repositório GitHub:** `MuriloSCunha0/BigKilo-Whatsapp` (Branch: `main`)
- **Serviço Web:** Django rodando em contêiner Docker (Nixpacks via Railway).
- **Banco de Dados:** PostgreSQL hospedado no Railway (Plugin PostgreSQL).
- **Domínio Público (Railway):** `web-production-51afd.up.railway.app`

## 3. Credenciais e Dados Importantes
> [!IMPORTANT]
> **Aviso de Segurança:** Estas credenciais são restritas e utilizadas nos testes atuais.

### Acesso Superuser (Esquema Público)
Utilizado para administrar domínios e tenants gerais no Django Admin (https://web-production-51afd.up.railway.app/admin/):
- **Usuário:** `admin`
- **Senha:** `admin` (ou `admin123` em caso de fallback local)

### Cliente Big Kilo (Esquema `bigkilo`)
O schema do Big Kilo foi "semeado" com o cardápio e credenciais próprias.
- **Login do restaurante:** `big kilo` (com espaço)
- **Senha:** `bigkilo123`
- **Telefone Registrado:** `21966263026`
- **Domínio mapeado:** `web-production-51afd.up.railway.app` (Este domínio acessa o schema do Big Kilo)

### Banco de Dados (Produção - Railway)
*(Descobertos durante testes e extrações locais)*
- **URL (Exemplo gerado na sessão):** `postgresql://postgres:HFZnkKKMuckLfWYZQCplMovDDtjHwiUU@tokaido.proxy.rlwy.net:52562/railway`
- **Variáveis de Conexão no Código:** Foram configurados *fallbacks* no `config/settings.py` para ler `DATABASE_URL`, `DATABASE_PRIVATE_URL`, `DATABASE_PUBLIC_URL` e até `PGHOST` / `PGPORT` para facilitar a ligação no Railway.

## 4. MCP Servers Disponíveis no Ambiente
O ambiente possui integração via MCP (Model Context Protocol) para gerenciamento direto de infraestrutura:
- **`railway`**: Disponibiliza as ferramentas para controlar o ambiente no Railway (`list_projects`, `list_variables`, `deploy`, `get_logs`, etc.). *Nota: Exige que a CLI do Railway (`railway login`) esteja autenticada no terminal do usuário para não dar erro "Unauthorized".*

## 5. Ponto de Bloqueio Atual (Blocker)
> [!WARNING]
> **Erro Crítico no Deploy do Railway**
> O último deploy automático no Railway está quebrando na inicialização (Startup) do contêiner, lançando o erro de banco de dados: `psycopg.OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused`.

**Causa:** O contêiner web não está recebendo as variáveis de ambiente com a URL do PostgreSQL. Quando não as encontra, o sistema tenta usar o localhost `127.0.0.1` e falha.
**Resolução Pendente:** O usuário precisa vincular manualmente a variável `DATABASE_URL` do banco de dados ao serviço do Django Web diretamente na interface gráfica do painel do Railway (Aba *Variables* -> *Add Reference* -> *PostgreSQL* -> *DATABASE_URL*).

## 6. Próximos Passos (Para a Nova Sessão)
1. **Validar a vinculação da Variável no Railway:** Assim que a nova sessão iniciar, certificar-se de que o Railway finalmente subiu o serviço em verde e o site `web-production-51afd.up.railway.app` está online.
2. **Testar o Fluxo de Conversa (Bot):** Realizar um teste simulado via terminal (usando a ferramenta já desenvolvida) ou via webhook para validar os casos limite do bot de pedidos, especialmente os problemas relatados anteriormente (ex: bot perguntando a data de encomenda múltiplas vezes).
3. **Setup Meta/WhatsApp:** Usar os guias gerados `whatsapp_setup_guide.md` e `tutorial_cliente_whatsapp.md` para auxiliar o cliente a criar o app de negócios no Facebook/Meta e validar o token de acesso da API do WhatsApp.
4. **Liberar a Produção:** Conectar de fato o webhook do Meta ao endereço em produção para o restaurante Big Kilo receber clientes reais.
