import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connection, transaction
from clientes.models import Cliente
from bot.fluxo import _core
from pedidos.models import SessaoBot

def run_test(telefone, interacoes):
    print("=" * 60)
    print(f" Iniciando Teste de Fluxo - Telefone: {telefone}")
    print("=" * 60)
    
    tenant = Cliente.objects.get(schema_name='bigkilo')
    connection.set_tenant(tenant)
    SessaoBot.objects.filter(telefone=telefone).delete()
    
    transcript = []
    
    for texto in interacoes:
        print(f"\nUsuario: {texto}")
        transcript.append(f"Usuario: {texto}")
        
        try:
            connection.close()
            connection.set_tenant(tenant)
            respostas = _core(telefone, texto, "Cliente Teste", None)
            
            for r in respostas["mensagens"]:
                msg_str = ""
                # r pode ser string ou objeto Resposta (que tem .texto, .opcoes_botoes, .opcoes_lista)
                if isinstance(r, str):
                    msg_str = r
                else:
                    msg_str = getattr(r, "texto", str(r))
                    botoes = getattr(r, "opcoes_botoes", [])
                    if botoes:
                        msg_str += "\n[Botões]: " + " | ".join(b.get("titulo", "") for b in botoes)
                    
                    lista = getattr(r, "opcoes_lista", [])
                    if lista:
                        msg_str += "\n[Lista]: " + " | ".join(o.get("titulo", "") for s in lista for o in s.get("opcoes", []))
                    
                    flows = getattr(r, "flows_nfm", False)
                    if flows:
                        msg_str += "\n[Fluxo Nativo do WhatsApp]"
                        
                transcript.append(f"Bot:\n{msg_str}")
        except Exception as e:
            transcript.append(f"Erro: {e}")

    with open("resultado_teste_fluxo.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(transcript))
    print("\nTeste concluído! Resultados salvos em resultado_teste_fluxo.txt")

def main():
    telefone_teste = "5521900000000"
    
    # 3. Define fluxo de mensagens
    interacoes = [
        "oi", # Saudação
        "1", # Escolhe Entrega
        "22640-101", # CEP (Barra da Tijuca)
        "1", # Montar Refeição Completa
        "hoje", # Consumo Hoje
        "1", # Proteína: Strogonoff
        "1", # Tamanho Padrão
        'multi:1,2,3', # Simulação retorno do NFM: Arroz, Feijão, Fritas
        "2", # Não quero adicionar novo produto
        "Rua dos Testes, 123, Apto 404", # Endereço Completo (Pulou a opção de entrega no checkout)
        "pix" # Pagamento Pix
    ]
    
    run_test(telefone_teste, interacoes)

if __name__ == "__main__":
    main()
