# applicant.py
import asyncio
import os
import tempfile
import random
from pathlib import Path
from playwright.async_api import async_playwright
from fpdf import FPDF

# ── Infos fixes Naïl (à déplacer dans config.py plus tard)
APPLICANT = {
    "gender": "m",
    "firstName": "Test",
    "lastName": "Test",
    "email": os.getenv("APPLICANT_EMAIL", "aphpjob@yopmail.com"),
    "phone": os.getenv("APPLICANT_PHONE", "600000000"),
}

async def human_delay(min=0.5, max=1.5):
    await asyncio.sleep(random.uniform(min, max))

def generate_lorem_pdf(title: str) -> str:
    """Génère un PDF lorem ipsum temporaire, retourne le path."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(200, 10, txt=title, ln=True)
    pdf.multi_cell(0, 10, txt=(
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. "
        "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum. "
        "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia. "
    ) * 5)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    pdf.output(tmp.name)
    return tmp.name


async def apply_to_job(job_url: str, job_title: str = "", headless: bool = True) -> bool:
    """
    Postule automatiquement à une offre APHP.
    Retourne True si succès, False sinon.
    """
    cv_path  = generate_lorem_pdf(f"CV - {APPLICANT['firstName']} {APPLICANT['lastName']}")
    lm_path  = generate_lorem_pdf(f"Lettre de motivation - {job_title}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="fr-FR"
            )
            page = await context.new_page()

            # ── 1. Ouvrir la page de l'offre
            print(f"   🌐 Ouverture : {job_url}")
            await page.goto(job_url, wait_until="networkidle", timeout=30000)
            await human_delay(1, 2)

            # ── 1.b Cookies
            print("   🍪 Acceptation cookies...")
            try:
                await page.locator("#tarteaucitronPersonalize2").click(timeout=5000)
                print("   ✅ Cookies acceptés")
            except:
                try:
                    await page.locator("#tarteaucitronAllDenied2").click(timeout=3000)
                    print("   ✅ Cookies refusés (fallback)")
                except:
                    print("   ⚠️  Pas de bandeau cookies détecté")
            await human_delay(1, 2)

            # ── 2. Cliquer sur "Postuler"
            print("   🖱 Clic sur Postuler...")
            await page.get_by_role("button", name="Postuler").first.click()
            await page.wait_for_selector("form.p-fluid", timeout=10000)

            # ── 3. Civilité
            print("   📝 Remplissage du formulaire...")
            gender_id = "m" if APPLICANT["gender"] == "m" else "f"
            await page.locator(f"input[type='radio'][id='{gender_id}']").check()

            # ── 4. Prénom / Nom / Email
            await page.locator("input[name='firstName']").fill(APPLICANT["firstName"])
            await page.locator("input[name='lastName']").fill(APPLICANT["lastName"])
            await page.locator("input[name='email']").fill(APPLICANT["email"])

            # ── 5. Téléphone
            phone_input = page.locator("input[name='phone']")
            await phone_input.fill("")
            await phone_input.type(APPLICANT["phone"])

            # ── 6. Upload CV
            print("   📎 Upload CV...")
            cv_input = page.locator("input[type='file']").nth(0)
            await cv_input.set_input_files(cv_path)
            await page.wait_for_timeout(1000)

            # ── 7. Upload Lettre de motivation
            print("   📎 Upload LM...")
            lm_input = page.locator("input[type='file']").nth(1)
            await lm_input.set_input_files(lm_path)
            await page.wait_for_timeout(1000)

            # ── 8. RQTH — PrimeReact dropdown
            print("   🔽 RQTH...")
            await page.locator(".p-dropdown").click()
            await page.wait_for_selector(".p-dropdown-panel", timeout=5000)
            await page.get_by_role("option", name="Non").click()

            # ── 9. CGU checkbox
            print("   ✅ Acceptation CGU...")
            await page.locator("input[id='accept']").check()

            # ── 10. Submit
            print("   🚀 Soumission...")
            await page.locator("button[type='submit']").click()

            # ── 11. Vérification succès
            # Attendre la disparition du formulaire ou un message de confirmation
            await page.wait_for_timeout(3000)
            form_still_open = await page.locator("form.p-fluid").is_visible()
            if not form_still_open:
                print("   ✅ Candidature soumise avec succès !")
                await browser.close()
                return True
            else:
                # Screenshot de debug si ça coince
                await page.screenshot(path="debug_apply.png")
                print("   ⚠️ Formulaire toujours ouvert — voir debug_apply.png")
                await browser.close()
                return False

    finally:
        # Nettoyage PDFs temporaires
        Path(cv_path).unlink(missing_ok=True)
        Path(lm_path).unlink(missing_ok=True)


def apply_sync(job_url: str, job_title: str = "", headless: bool = True) -> bool:
    """Wrapper synchrone pour appel depuis pipeline.py."""
    return asyncio.run(apply_to_job(job_url, job_title, headless))


if __name__ == "__main__":
    # Test direct
    result = apply_sync(
        job_url="https://recrutement.aphp.fr/jobs/777439",
        job_title="Infirmier en secteur de Maladies Infectieuses et Tropicales F/H ",
        headless=True  # False = voir le navigateur pendant le test
    )
    print(f"\nRésultat : {'✅ Succès' if result else '❌ Échec'}")