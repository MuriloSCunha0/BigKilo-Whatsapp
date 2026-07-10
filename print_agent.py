"""
Agente de impressão automática da comanda do Big Kilo.

Roda no COMPUTADOR do restaurante (o que tem a impressora). NÃO precisa do
Django nem acesso ao banco: ele conversa com o servidor por uma API segura
(token), busca os pedidos pagos e imprime a comanda AUTOMATICAMENTE.

Variáveis de ambiente:
  PRINT_API_URL    : URL do sistema. Ex.: https://seu-app.up.railway.app
  PRINT_API_TOKEN  : mesmo valor de IMPRESSAO_API_TOKEN no servidor.
  PRINT_POLL_SECONDS : intervalo entre verificações (padrão 5).
  PRINT_MODE       : file (padrão/demo) | windows | escpos
    - windows : PRINTER_NAME (vazio = impressora padrão). Requer 'pywin32'.
    - escpos  : PRINTER_HOST / PRINTER_PORT (padrão 9100). Requer 'python-escpos'.

Uso: python print_agent.py
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

API = os.getenv("PRINT_API_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("PRINT_API_TOKEN", "")
INTERVALO_S = int(os.getenv("PRINT_POLL_SECONDS", "5"))
PRINT_MODE = os.getenv("PRINT_MODE", "file").lower()
PRINTER_NAME = os.getenv("PRINTER_NAME", "")
PRINTER_HOST = os.getenv("PRINTER_HOST", "")
PRINTER_PORT = int(os.getenv("PRINTER_PORT", "9100"))
COMANDAS_DIR = Path(__file__).resolve().parent / "comandas"


# ---- HTTP (stdlib, sem dependências) ----
def _req(caminho, dados=None):
    url = f"{API}{caminho}"
    headers = {"X-Print-Token": TOKEN, "Content-Type": "application/json"}
    body = json.dumps(dados).encode() if dados is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def buscar_pendentes():
    return _req("/pedidos/impressao/pendentes/").get("pedidos", [])


def marcar_impresso(pedido_id):
    return _req("/pedidos/impressao/marcar/", {"pedido_id": pedido_id})


# ---- Impressão ----
def imprimir_file(texto, pid):
    COMANDAS_DIR.mkdir(exist_ok=True)
    (COMANDAS_DIR / f"pedido_{pid}.txt").write_text(texto, encoding="utf-8")
    print(f"[file] Comanda do pedido #{pid} salva em {COMANDAS_DIR}")


def imprimir_windows(texto, pid):
    import win32print  # type: ignore

    nome = PRINTER_NAME or win32print.GetDefaultPrinter()
    h = win32print.OpenPrinter(nome)
    try:
        win32print.StartDocPrinter(h, 1, (f"Comanda {pid}", None, "RAW"))
        win32print.StartPagePrinter(h)
        win32print.WritePrinter(h, texto.encode("cp850", errors="replace"))
        win32print.EndPagePrinter(h)
        win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)
    print(f"[windows] Comanda do pedido #{pid} enviada para '{nome}'")


def imprimir_escpos(texto, pid):
    from escpos.printer import Network  # type: ignore

    p = Network(PRINTER_HOST, port=PRINTER_PORT, timeout=10)
    p.text(texto + "\n")
    p.cut()
    print(f"[escpos] Comanda do pedido #{pid} enviada para {PRINTER_HOST}:{PRINTER_PORT}")


IMPRESSORAS = {"file": imprimir_file, "windows": imprimir_windows, "escpos": imprimir_escpos}


def processar_pendentes():
    imprimir = IMPRESSORAS.get(PRINT_MODE, imprimir_file)
    for pedido in buscar_pendentes():
        try:
            imprimir(pedido["comanda"], pedido["id"])
            marcar_impresso(pedido["id"])
        except Exception as exc:
            print(f"[erro] Falha ao imprimir pedido #{pedido.get('id')}: {exc}")


def main():
    if not TOKEN:
        print("⚠️  Defina PRINT_API_TOKEN (igual ao IMPRESSAO_API_TOKEN do servidor).")
        return
    print(f"Agente de impressão Big Kilo (api={API}, modo={PRINT_MODE}, intervalo={INTERVALO_S}s).")
    print("Aguardando pedidos pagos... (Ctrl+C para sair)")
    while True:
        try:
            processar_pendentes()
        except urllib.error.URLError as exc:
            print(f"[rede] Sem conexão com o servidor: {exc}")
        except Exception as exc:
            print(f"[erro] Loop: {exc}")
        time.sleep(INTERVALO_S)


if __name__ == "__main__":
    main()
