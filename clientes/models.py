from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class Cliente(TenantMixin):
    nome = models.CharField(max_length=100)
    criado_em = models.DateField(auto_now_add=True)

    # schema_name is automatically created by TenantMixin
    ativo = models.BooleanField(default=True)
    telefone_whatsapp = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        help_text="Número do WhatsApp conectado ao bot (ex: 5521999999999)"
    )

    def __str__(self):
        return self.nome

class Dominio(DomainMixin):
    pass
