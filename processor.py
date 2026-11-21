"""processor.py - Pastron tekstin, heq të dhënat personale dhe e përkthen në anglisht.

Anglishtja është gjuha e përbashkët që extractor.py punon me një prompt të vetëm.
Gjuha origjinale mbetet te kolona 'gjuha'.
"""
import json
import os
import re
import sys
import time
import urllib.request

import db

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODELI = os.environ.get("OLLAMA_MODEL", "deepseek-r1:8b")  # ose ndryshoje këtu
MAX_KARAKTERE = 4000        # artikujt e gjatë priten; ngjarja zakonisht është në fillim
COPA = 1500                 # sa karaktere përkthehen në një thirrje

GJUHET = {"sq": "Albanian", "sr": "Serbian"}

# Të dhëna personale që nuk duhet të ruhen
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TELEFON = re.compile(r"(?<!\d)(?:\+|00)?\d[\d\s/.-]{7,}\d(?!\d)")


def pastro(teksti):
    """Heq email-et, numrat e telefonit dhe hapësirat e tepërta."""
    teksti = EMAIL.sub("[email]", teksti or "")
    # vetëm vargje me 9+ shifra, që datat (20.11.2026) dhe vitet të mbeten
    teksti = TELEFON.sub(
        lambda m: "[telefon]" if sum(c.isdigit() for c in m.group()) >= 9 else m.group(), teksti)
    teksti = re.sub(r"[ \t]+", " ", teksti)
    return re.sub(r"\n{3,}", "\n\n", teksti).strip()[:MAX_KARAKTERE]


def ndaj_ne_copa(teksti):
    """Ndan tekstin në copa të kufizuara, duke preferuar fund paragrafin ose fjalën."""
    copa = []
    teksti = teksti.strip()
    while len(teksti) > COPA:
        kufiri = teksti.rfind("\n", 0, COPA + 1)
        if kufiri <= 0:
            kufiri = teksti.rfind(" ", 0, COPA + 1)
        kufiri = kufiri if kufiri > 0 else COPA
        copa.append(teksti[:kufiri].rstrip())
        teksti = teksti[kufiri:].lstrip()
    if teksti:
        copa.append(teksti)
    return copa


def gabimi_ollama():
    """Kthen arsyen e mosgatishmërisë ose None kur gjendet modeli i konfiguruar."""
    baza = OLLAMA_URL.rsplit("/api/", 1)[0].rstrip("/")
    try:
        with urllib.request.urlopen(f"{baza}/api/tags", timeout=5) as pergjigjja:
            katalogu = json.load(pergjigjja)
    except OSError:
        return "Ollama nuk po përgjigjet. Nise me 'ollama serve' dhe provo përsëri."
    except ValueError:
        return "Përgjigjja nga Ollama /api/tags është e pavlefshme."
    modelet = katalogu.get("models") if isinstance(katalogu, dict) else None
    if not isinstance(modelet, list):
        return "Përgjigjja nga Ollama /api/tags nuk përmban listën e modeleve."
    for modeli in modelet:
        emri = (modeli.get("model") or modeli.get("name")) if isinstance(modeli, dict) else None
        if isinstance(emri, str) and emri.removesuffix(":latest") == MODELI.removesuffix(":latest"):
            return None
    return f"Modeli '{MODELI}' mungon në Ollama. Kontrollo OLLAMA_MODEL ose instalo modelin."


def ollama_gati():
    return gabimi_ollama() is None


def pyet_ollama(prompt, si_json=False):
    """Thirrje e thjeshtë te Ollama lokal; kthen vetëm përgjigjen (pa <think>).
    si_json=True e detyron modelin të kthejë JSON të vlefshëm."""
    kerkesa = {"model": MODELI, "prompt": prompt, "stream": False,
               "think": False, "options": {"temperature": 0}}
    if si_json:
        kerkesa["format"] = "json"
    trupi = json.dumps(kerkesa).encode()
    req = urllib.request.Request(OLLAMA_URL, data=trupi,
                                 headers={"Content-Type": "application/json"})
    # Ollama ndonjëherë kthen 500 (p.sh. kur modeli ringarkohet); riprovo 2 herë
    for prova in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                rezultati = json.load(r)
            pergjigja = rezultati.get("response") if isinstance(rezultati, dict) else None
            if not isinstance(pergjigja, str) or not pergjigja.strip():
                raise ValueError("Ollama ktheu përgjigje bosh ose të pavlefshme.")
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or prova == 2:
                raise
        except urllib.error.URLError:
            if prova == 2:
                raise
        time.sleep(5 * (prova + 1))
    # modelet "reasoning" ndonjëherë e shtojnë mendimin në tekst; hiqe
    pergjigja = re.sub(r"<think>.*?</think>", "", pergjigja, flags=re.S).strip()
    if not pergjigja:
        raise ValueError("Ollama ktheu vetëm tekst mendimi.")
    return pergjigja


def perkthe(teksti, gjuha):
    """Përkthen në anglisht. Anglishtja dhe gjuhët e panjohura kthehen siç janë."""
    if gjuha == "en":
        return teksti
    burimi = GJUHET.get(gjuha, "the original language")
    pjeset = []
    for c in ndaj_ne_copa(teksti):
        pjeset.append(pyet_ollama(
            f"Translate this news text from {burimi} to English. "
            f"Output only the translation, nothing else.\n\n{c}"))
    return "\n".join(pjeset)


def perpuno(limit=20):
    """Kalon artikujt pa përkthim. Kthen (te_sukseshem, me_gabim)."""
    ok = gabime = 0
    for a in db.artikuj_pa_perkthim(limit):
        t0 = time.time()
        try:
            teksti = pastro(f"{a['titulli']}\n\n{a['teksti']}")
            db.ruaj_perkthimin(a["id"], teksti, perkthe(teksti, a["gjuha"]))
            ok += 1
            print(f"  #{a['id']} [{a['gjuha']}] ok ({time.time() - t0:.0f}s)")
        except Exception as e:
            # mos e ndal gjithë punën për një artikull; provohet sërish herën tjetër
            gabime += 1
            print(f"  #{a['id']} gabim: {e}")
    return ok, gabime


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    ok, gabime = perpuno(n)
    print(f"\nU përpunuan {ok}, gabime {gabime}.")
