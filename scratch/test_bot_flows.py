import os
import sys
import django

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from bot.fluxo import _core
from pedidos.models import SessaoBot
from clientes.models import Cliente
from unittest.mock import patch

def mock_asaas(*args, **kwargs):
    return {"id": "cus_123"}, None

def mock_cobranca(*args, **kwargs):
    return {"invoiceUrl": "http://fake.url", "payload": "00020126580014BR.GOV.BCB.PIX..."}, None



def setup_test():
    tenant = Cliente.objects.exclude(schema_name="public").first()
    if tenant:
        from django.db import connection
        connection.set_schema(tenant.schema_name)
    SessaoBot.objects.filter(telefone="00000000000").delete()
    
    # Criar area de entrega para o CEP passar!
    from pedidos.models import AreaEntrega
    AreaEntrega.objects.get_or_create(bairro="Recreio", defaults={"cep_inicio": "22790000", "cep_fim": "22790999"})


def run_flow(name, inputs):
    print(f"\n====================================")
    print(f"RUNNING FLOW: {name}")
    print(f"====================================")
    setup_test()
    with patch("pagamentos.pix_whatsapp.montar_mensagens_pix", return_value=["Pix mockado"]):
        for txt in inputs:
            print(f"\n[USUÁRIO]: {txt}")
            res = _core("00000000000", txt, nome="Testador")
            for msg in res.get("mensagens", []):
                if isinstance(msg, dict):
                    print(f"[BOT]: [MENSAGEM ESTRUTURADA - {msg.get('tipo')}] {msg.get('corpo', '')}")
                else:
                    print(f"[BOT]: {msg}")

def main():
    run_flow("FLUXO 1 - Delivery Individual Completo", [
        "oi",          
        "1",           
        "22790000", 
        "1",           
        "1",           
        "1",           
        "1",           
        "pronto",      
        "fechar",      
        "2",           
        "1",           
        "Minha Rua, 10, Apto 2", 
        "Tijuca",      
        "1",           
    ])

    run_flow("FLUXO 2 - Retirada Misto (Individual + Grande)", [
        "oi",          
        "2",           
        "1",           
        "1",           
        "1",           
        "1",           
        "pronto",      
        "fechar",      
        "1",           
        "2",           
        "1",           
        "fechar",      
        "1",           
        "1",           
    ])

    run_flow("FLUXO 3 - Encomenda de Data", [
        "oi",
        "1",           
        "22790000",    # CEP que eu sei que deve estar na area de entrega ou pelo menos vai ter logica. Wait, 22000-000 is Copacabana, 22790000 is Recreio. The DB might be empty. Let's create an area!
        "3",           
        "amanhã",      
        "meio dia",    
        "1",           
        "1",           
        "1",           
        "1",           
        "pronto",      
        "fechar",      
        "2",           
        "1",           
        "Rua da encomenda, 100", 
        "Centro",      
        "1",           
    ])
    print("\n[TESTES FINALIZADOS COM SUCESSO]")

if __name__ == "__main__":
    main()
