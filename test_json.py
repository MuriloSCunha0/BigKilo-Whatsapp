import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connection
from clientes.models import Cliente
from pedidos.models import SessaoBot

def test():
    tenant = Cliente.objects.filter(schema_name='bigkilo').first()
    if not tenant:
        print("No tenant")
        return
    connection.set_tenant(tenant)
    SessaoBot.objects.all().delete()
    s = SessaoBot.objects.create(telefone="1234")
    
    # Mutate in-place
    s.carrinho_json["encomenda"] = {"data": "2026-11-25T00:00:00"}
    s.save()
    
    # Reload
    s.refresh_from_db()
    print("After in-place mutation:", s.carrinho_json.get("encomenda"))
    
    # Mutate via reassignment
    c = s.carrinho_json
    c["encomenda"] = {"data": "2026-11-26T00:00:00"}
    s.carrinho_json = c
    s.save()
    
    s.refresh_from_db()
    print("After reassignment:", s.carrinho_json.get("encomenda"))

test()
