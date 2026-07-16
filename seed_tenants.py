import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from clientes.models import Cliente, Dominio

def create_tenants():
    # Cria o schema public
    if not Cliente.objects.filter(schema_name='public').exists():
        tenant = Cliente(schema_name='public', nome='Orquestrador')
        tenant.save()
        
        domain = Dominio()
        domain.domain = 'localhost' # or any host
        domain.tenant = tenant
        domain.is_primary = True
        domain.save()
        print("Schema public criado.")
    else:
        print("Schema public ja existe.")

    # Cria o tenant bigkilo
    if not Cliente.objects.filter(schema_name='bigkilo').exists():
        tenant = Cliente(schema_name='bigkilo', nome='Big Kilo')
        tenant.save()

        domain = Dominio()
        domain.domain = 'bigkilo.localhost'
        domain.tenant = tenant
        domain.is_primary = True
        domain.save()
        print("Schema bigkilo criado.")
    else:
        print("Schema bigkilo ja existe.")

if __name__ == '__main__':
    create_tenants()
