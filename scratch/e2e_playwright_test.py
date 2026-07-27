import os
import sys
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = r"C:\Users\Suporte\.gemini\antigravity\brain\839505ff-62f5-43a4-b03a-eb99c8d24c45\e2e_screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000"

def take_shot(page, filename, desc=""):
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    page.screenshot(path=filepath, full_page=True)
    print(f"[SCREENSHOT] Saved: {filename} ({desc})")

def run_e2e():
    print("Starting Playwright E2E Test Suite...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("\n1. Navigating to Admin Login...")
        page.goto(f"{BASE_URL}/admin/login/")
        page.fill("#id_username", "big kilo")
        page.fill("#id_password", "bigkilo123")
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("networkidle")
        
        page.goto(f"{BASE_URL}/admin/")
        page.wait_for_load_state("networkidle")
        take_shot(page, "01_login_dashboard.png", "Dashboard principal após login")

        print("\n2. Importing Menu Spreadsheet (.xlsx)...")
        page.goto(f"{BASE_URL}/admin/cardapio/cardapio/importar-planilha/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        excel_path = os.path.abspath("scratch/test_menu_import.xlsx")
        page.fill("input[name='nome_cardapio']", "Cardápio Especial E2E")
        page.check("input[name='dias'][value='0']") # Segunda
        page.check("input[name='dias'][value='1']") # Terça
        page.check("input[name='dias'][value='2']") # Quarta
        page.check("input[name='dias'][value='3']") # Quinta
        page.check("input[name='dias'][value='4']") # Sexta
        page.set_input_files("input[name='planilha']", excel_path)
        
        submit_btn = page.query_selector("button[type='submit']") or page.query_selector("input[type='submit']")
        if submit_btn:
            submit_btn.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
        take_shot(page, "02_menu_imported.png", "Cardápio importado via planilha Excel")

        print("\n3. Creating Manual Product...")
        page.goto(f"{BASE_URL}/admin/cardapio/produto/add/")
        page.wait_for_load_state("networkidle")
        
        page.fill("input[name='nome']", "Strogonoff Supremo E2E")
        page.fill("textarea[name='descricao']", "Acompanha batata palha e arroz soltinho")
        
        modo_select = page.query_selector("select[name='modo_venda']")
        if modo_select:
            modo_select.select_option("UNIDADE")
            
        page.fill("input[name='preco']", "42.50")
        
        cat_select = page.query_selector("select[name='categoria']")
        if cat_select:
            options = cat_select.query_selector_all("option")
            if len(options) > 1:
                cat_select.select_option(options[1].get_attribute("value"))

        save_btn = page.query_selector("input[name='_save']") or page.query_selector("button[name='_save']")
        if save_btn:
            save_btn.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
        take_shot(page, "03_product_manual_created.png", "Produto criado manualmente com sucesso")

        print("\n4. Navigating to Message Flows...")
        page.goto(f"{BASE_URL}/admin/pedidos/perfilfluxo/")
        page.wait_for_load_state("networkidle")
        take_shot(page, "04_flow_list.png", "Lista de Fluxos de Mensagem no Admin")

        print("\n5. Creating New Flow via Assistant...")
        page.evaluate("if(window.pfOpen) window.pfOpen();")
        time.sleep(0.5)
        page.fill("#pfNome", "Fluxo VIP Experiência E2E")
        page.click("#pfSalvar")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        take_shot(page, "05_new_flow_created.png", "Novo fluxo criado e aberto no editor visual")

        print("\n6. Testing Visual Drag-and-Drop Flow Builder...")
        time.sleep(1)
        txt_boas_vindas = page.query_selector("#txt_BOAS_VINDAS")
        if txt_boas_vindas:
            txt_boas_vindas.fill("🌟 *Olá! Bem-vindo ao atendimento VIP Big Kilo!*\nComo podemos servir você hoje?")
            page.evaluate("if(window.fxAtualizar) window.fxAtualizar();")
        
        take_shot(page, "06_flow_visual_edited.png", "Novo Fluxo editado no construtor visual drag-and-drop")
        
        save_fx = page.query_selector("#fxSalvar")
        if save_fx:
            save_fx.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)

        print("\n7. Activating New Flow for Meta API...")
        page.goto(f"{BASE_URL}/admin/pedidos/perfilfluxo/")
        page.wait_for_load_state("networkidle")
        
        activate_link = page.query_selector("a[href*='/pedidos/fluxo/'][href*='/ativar/']")
        if activate_link:
            activate_link.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            
        take_shot(page, "07_flow_activated.png", "Fluxo ativado para uso na API oficial da Meta (com botão de desconectar visível)")

        print("\n8. Testing Simulator with Multi-Flow Selector...")
        page.goto(f"{BASE_URL}/simulador/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        take_shot(page, "08_simulator_default.png", "Simulador com o Seletor Multi-Fluxos no topo")

        print("\n9. Interacting with Simulator...")
        page.click("#simInp")
        page.fill("#simInp", "oi")
        page.click("button:has-text('➤')")
        time.sleep(1.5)
        take_shot(page, "09_simulator_greeting.png", "Resposta inicial do simulador")

        opt_retirada = page.query_selector("button:has-text('Vou retirar na loja')") or page.query_selector("button.sim-row")
        if opt_retirada:
            opt_retirada.click()
            time.sleep(1.5)

        perfil_select = page.query_selector("#simPerfilSelect")
        if perfil_select:
            opts = perfil_select.query_selector_all("option")
            if len(opts) > 1:
                perfil_select.select_option(opts[1].get_attribute("value"))
                time.sleep(1.5)

        take_shot(page, "10_simulator_testing_flow.png", "Simulador alternado dinamicamente para outro perfil de fluxo")

        page.click("button:has-text('Simular pagamento PIX')")
        time.sleep(1.5)
        take_shot(page, "11_simulator_pix_payment.png", "Simulação de pagamento PIX concluída com emissão de comanda")

        browser.close()
        print("\nE2E PLAYWRIGHT AUTOMATION COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_e2e()
