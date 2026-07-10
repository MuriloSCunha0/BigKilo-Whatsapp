# Revisão de UX — Painel Big Kilo (pente fino)

Auditoria navegando todas as telas/fluxos no navegador (24/06/2026). Itens
ordenados por impacto para o lojista (usuário final, não técnico).

## 🔴 Alta prioridade (confunde/atrapalha ou é arriscado)

1. **Conversas (WhatsApp) expõe "Carrinho (JSON)" cru e editável**
   Ex.: `{"endereco": {}, "itens": [], "_menu": {...}}`. Técnico e perigoso (editar quebra a conversa).
   → Tornar a tela **somente leitura** com um resumo amigável (estado + última atualização) e uma ação "Reiniciar conversa". Esconder o JSON.

2. **Simulador não reinicia ao abrir**
   Se o telefone de teste tem uma sessão antiga, abre com *"Opção inválida. Envie o número do seu bairro"* em vez da saudação.
   → Resetar a sessão automaticamente ao abrir o simulador (como o botão "Reiniciar").

3. **Textos em inglês** (padrão do Unfold não traduzido)
   "Type to search", "Filters" (todas as listas) e a aba **"General"** no Pedido.
   → Traduzir para "Buscar", "Filtros", "Geral".

4. **"Áreas de entrega" abre a página antiga ao clicar em "+"** (não o modal)
   Inconsistente com Produto/Categoria/Cardápio/Promoção (que abrem modal).
   → Modal de 1 passo (bairro + faixa de CEP).

## 🟡 Média prioridade

5. **"tier (montagem)" na coluna Preço dos Produtos** — jargão técnico.
   → Trocar por algo como "Por peso (tabela da loja)".

6. **Tela de Pedido** — vem do bot, mas tem campos editáveis demais:
   Cliente e Valor total editáveis; **Endereço** é uma caixa de texto gigante.
   → Deixar a maior parte **somente leitura** (editar só o Status) e reduzir o textarea do endereço.

7. **Bot não reconhece saudação no meio do fluxo**
   Cliente que volta e manda "oi" no meio recebe *"Opção inválida"*.
   → Tratar "oi/olá/menu/início" como reinício gentil em qualquer etapa (ajuda o cliente real, não só o simulador).

## 🟢 Baixa prioridade (polimento)

8. **Dashboard** — KPIs são só de "hoje" (mostram 0 num dia parado) e "Mais/Menos vendidos" repetem os mesmos itens quando há poucos dados.
   → Rotular "(hoje)" e/ou opção de 7 dias; ocultar "menos vendidos" quando há poucos itens.

9. **Produto › Faixas de preço** — campo "Ordem" é detalhe técnico exposto.
   → Tornar automático/ocultar.

10. **Fluxos de mensagem** — coluna "Mensagens personalizadas" mostra 8 no Padrão (são as do fluxo, não "personalizadas").
    → Renomear coluna para "Mensagens".

11. **Grade de horários (cardápio)** — rótulos "Almoço/Jantar" ficam soltos à direita dos checkboxes.
    → Melhorar alinhamento das colunas.

## ✅ Telas que estão muito boas (manter)
- Assistente de **Produto** (4 passos), **Cardápio** (4 passos, com grade de dias e seletor de produtos com busca), **Categoria** e **Promoção** (modais).
- **Editor de fluxo** (passos numerados, "quando aparece", variável `{bairro}` explicada e travada).
- **Perfil do contato** e o **editor de mensagens do contato** (mostra o padrão x personalizado).
- **Linha inteira clicável** nas listas.
