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
import sys
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


def _bytes_escpos(texto: str) -> bytes:
    """Monta os bytes ESC/POS: init + codepage PT (PC850) + texto + avanço + corte.

    Funciona na ELGIN i9 (e na maioria das térmicas ESC/POS 80mm) via impressão RAW.
    """
    ESC, GS = b"\x1b", b"\x1d"
    return (
        ESC + b"@"                                   # inicializa a impressora
        + ESC + b"t" + b"\x02"                        # codepage PC850 (acentos: ã, ç, õ…)
        + texto.encode("cp850", errors="replace")    # corpo da comanda
        + b"\n"
        + ESC + b"d" + b"\x04"                        # avança 4 linhas (folga p/ o corte)
        + GS + b"V" + b"\x01"                         # corte parcial do papel
    )


def _achar_impressora(win32print, preferida):
    """Usa o nome exato se existir; senão acha a ELGIN/i9 sozinho; senão a padrão."""
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    nomes = [p[2] for p in win32print.EnumPrinters(flags)]
    if preferida and preferida in nomes:
        return preferida
    for n in nomes:  # tolera variações: "ELGIN i9", "Elgin i9 (USB)", etc.
        low = n.lower()
        if "elgin" in low or "i9" in low:
            return n
    return preferida or win32print.GetDefaultPrinter()


def imprimir_windows(texto, pid):
    import win32print  # type: ignore

    nome = _achar_impressora(win32print, PRINTER_NAME)
    h = win32print.OpenPrinter(nome)
    try:
        win32print.StartDocPrinter(h, 1, (f"Comanda {pid}", None, "RAW"))
        win32print.StartPagePrinter(h)
        win32print.WritePrinter(h, _bytes_escpos(texto))
        win32print.EndPagePrinter(h)
        win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)
    print(f"[windows] Comanda do pedido #{pid} enviada para '{nome}' (com corte).")


def imprimir_escpos(texto, pid):
    from escpos.printer import Network  # type: ignore

    p = Network(PRINTER_HOST, port=PRINTER_PORT, timeout=10)
    p.text(texto + "\n")
    p.cut()
    print(f"[escpos] Comanda do pedido #{pid} enviada para {PRINTER_HOST}:{PRINTER_PORT}")


IMPRESSORAS = {"file": imprimir_file, "windows": imprimir_windows, "escpos": imprimir_escpos}

impressos_cache = set()

def processar_pendentes():
    imprimir = IMPRESSORAS.get(PRINT_MODE, imprimir_file)
    for pedido in buscar_pendentes():
        pid = pedido["id"]
        if pid in impressos_cache:
            try:
                marcar_impresso(pid)
            except Exception:
                pass
            continue
            
        try:
            imprimir(pedido["comanda"], pid)
            impressos_cache.add(pid)
            marcar_impresso(pid)
        except Exception as exc:
            print(f"[erro] Falha ao imprimir pedido #{pid}: {exc}")


COMANDA_TESTE = "\n".join([
    "=" * 40,
    "           BIG KILO - TESTE".ljust(40),
    "=" * 40,
    "Se voce esta lendo isto na ELGIN i9,",
    "a impressao automatica esta FUNCIONANDO!",
    "",
    "Acentos: pao, acucar, limao, feijao",
    "Pedido #0000  -  R$ 57,00",
    "=" * 40,
    "",
])


def listar_impressoras():
    try:
        import win32print  # type: ignore
    except ImportError:
        print("Instale o pywin32:  pip install pywin32")
        return
    print("Impressora padrão:", win32print.GetDefaultPrinter())
    print("Impressoras instaladas:")
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    for p in win32print.EnumPrinters(flags):
        print("  -", p[2])


def testar_impressao():
    imprimir = IMPRESSORAS.get(PRINT_MODE, imprimir_file)
    print(f"Enviando comanda de TESTE (modo={PRINT_MODE}, impressora='{PRINTER_NAME or 'padrão'}')...")
    imprimir(COMANDA_TESTE, "TESTE")
    print("Pronto. Confira se saiu na impressora.")


def _pasta_estavel():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "BigKiloImpressora"


def _registrar_run(caminho_exe):
    import winreg
    chave = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(chave, "BigKiloImpressora", 0, winreg.REG_SZ, f'"{caminho_exe}"')
    winreg.CloseKey(chave)


def _garantir_instalado():
    """Só quando roda como .exe: copia para uma pasta fixa e registra o início
    automático com o Windows. Retorna True se copiou e relançou (o atual deve sair)."""
    if not getattr(sys, "frozen", False):
        return False  # em modo script (dev) não mexe em nada
    try:
        destino_dir = _pasta_estavel()
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / "BigKiloImpressora.exe"
        atual = Path(sys.executable)
        if atual.resolve() != destino.resolve():
            import shutil
            shutil.copy2(atual, destino)      # instala numa pasta permanente
            _registrar_run(destino)           # liga sozinho com o Windows
            os.startfile(str(destino))        # passa a rodar da pasta fixa
            print("[instalado] Configurado para ligar sozinho com o Windows. ✅")
            return True
        _registrar_run(destino)               # já está na pasta fixa: só garante o auto-start
    except Exception as exc:
        print(f"[instalar] {exc}")
    return False


def _minimizar_console():
    """Deixa a janelinha minimizada (fora do caminho do caixa)."""
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # 6 = SW_MINIMIZE
    except Exception:
        pass


def main():
    if "--listar" in sys.argv:
        listar_impressoras()
        return
    if "--teste" in sys.argv:
        testar_impressao()
        return
    if not TOKEN:
        print("⚠️  Defina PRINT_API_TOKEN (igual ao IMPRESSAO_API_TOKEN do servidor).")
        return
    if _garantir_instalado():
        return  # relançou da pasta fixa; este processo encerra
    _minimizar_console()
    print(f"Agente de impressão Big Kilo (api={API}, modo={PRINT_MODE}, intervalo={INTERVALO_S}s).")
    print("Aguardando pedidos pagos... (Ctrl+C para sair)")
    intervalo_atual = INTERVALO_S
    while True:
        try:
            processar_pendentes()
            intervalo_atual = INTERVALO_S  # reset backoff
        except urllib.error.URLError as exc:
            print(f"[rede] Sem conexão com o servidor: {exc}. Retentando em {intervalo_atual}s...")
            time.sleep(intervalo_atual)
            intervalo_atual = min(intervalo_atual * 2, 60)
            continue
        except Exception as exc:
            print(f"[erro] Loop: {exc}")
        time.sleep(intervalo_atual)


if __name__ == "__main__":
    main()
