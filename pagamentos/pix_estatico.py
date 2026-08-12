"""Gerador de Pix 'copia e cola' (BR Code / EMV) — 100% local, sem gateway.

Cria um payload Pix pagável a partir da CHAVE do restaurante + valor exato.
Não há confirmação automática (sem webhook): o lojista confirma o pagamento no
painel quando o Pix cair. Usado quando não há Asaas disponível.

Especificação: Manual do BR Code / Pix (Banco Central).
"""

import unicodedata
from decimal import Decimal, ROUND_HALF_UP


def _ascii_maiusc(texto: str, tam: int) -> str:
    """Só letras/números/espaço, sem acento, MAIÚSCULO (exigência do BR Code)."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(c for c in s if c.isalnum() or c == " ")
    return (" ".join(s.upper().split()))[:tam] or "NA"


def _tlv(campo: str, valor: str) -> str:
    """Monta um campo EMV no formato ID + tamanho(2 dígitos) + valor."""
    return f"{campo}{len(valor):02d}{valor}"


def _crc16(payload: str) -> str:
    """CRC16-CCITT (poly 0x1021, init 0xFFFF) — exigido no fim do BR Code."""
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def gerar_pix_copia_cola(chave: str, valor, nome: str = "Big Kilo",
                         cidade: str = "RIO DE JANEIRO", txid: str = "***") -> str:
    """Retorna o Pix 'copia e cola' com o valor embutido, pronto para pagar."""
    chave = str(chave or "").strip()
    if not chave:
        raise ValueError("Chave Pix não configurada.")

    valor_str = f"{Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    nome = _ascii_maiusc(nome, 25)
    cidade = _ascii_maiusc(cidade, 15)
    txid_limpo = "".join(c for c in str(txid or "***") if c.isalnum()) or "***"
    txid_limpo = txid_limpo[:25]

    merchant_account = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    dados_adicionais = _tlv("05", txid_limpo)

    payload = (
        _tlv("00", "01")                    # Payload Format Indicator
        + _tlv("26", merchant_account)      # Merchant Account Information (Pix)
        + _tlv("52", "0000")                # Merchant Category Code
        + _tlv("53", "986")                 # Moeda: 986 = BRL
        + _tlv("54", valor_str)             # Valor da transação
        + _tlv("58", "BR")                  # País
        + _tlv("59", nome)                  # Nome do recebedor
        + _tlv("60", cidade)                # Cidade do recebedor
        + _tlv("62", dados_adicionais)      # Dados adicionais (txid)
        + "6304"                            # CRC (id + tam), valor calculado abaixo
    )
    return payload + _crc16(payload)
