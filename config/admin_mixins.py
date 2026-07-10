"""Mixins reutilizáveis para o Django Admin.

`Localized*Mixin`: faz os campos numéricos do admin aceitarem o formato
brasileiro (vírgula como separador decimal, ex.: "8,00"). Sem isso, o usuário
digita "8,00" e o valor é interpretado errado.
"""

from django import forms
from django.forms.widgets import NumberInput, TextInput


def _localizar_numeros(base_fields):
    for campo in base_fields.values():
        if isinstance(campo, (forms.DecimalField, forms.FloatField)):
            campo.localize = True
            # <input type="number"> bloqueia a vírgula no navegador. Trocamos por um
            # campo de texto localizado: aceita "8,00" (e também "8.00") e converte certo.
            if isinstance(campo.widget, NumberInput):
                attrs = {k: v for k, v in campo.widget.attrs.items() if k != "step"}
                attrs["inputmode"] = "decimal"
                campo.widget = TextInput(attrs=attrs)
            campo.widget.is_localized = True
        elif isinstance(campo, forms.IntegerField):
            campo.localize = True
            if hasattr(campo.widget, "is_localized"):
                campo.widget.is_localized = True


class LocalizedAdminMixin:
    """Para ModelAdmin: localiza os campos numéricos do formulário principal."""

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        _localizar_numeros(form.base_fields)
        return form


class LocalizedInlineMixin:
    """Para Inlines: localiza os campos numéricos do formulário do inline."""

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        _localizar_numeros(formset.form.base_fields)
        return formset
