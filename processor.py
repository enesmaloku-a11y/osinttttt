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
# Vetëm me LLM_PROVIDER=featherless teksti dërgohet te një API në cloud (p.sh. demo në Railway);
# parazgjedhja mbetet Ollama lokal, që laptopi i analistit të mos dërgojë asgjë jashtë pa e ditur.
FEATHERLESS_URL = os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1").rstrip("/") + "/chat/completions"
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
    """Ndan tekstin në paragrafë deri në COPA karaktere, që modeli të mos humbasë."""
    copa, aktuale = [], ""
    for p in teksti.split("\n"):
        if aktuale and len(aktuale) + len(p) > COPA:
            copa.append(aktuale)
            aktuale = ""
        aktuale += p + "\n"
    if aktuale.strip():
        copa.append(aktuale)
    return copa


def ollama_gati():
    """True nëse Ollama lokal përgjigjet (kontroll i shpejtë para pipeline-it)."""
    baza = OLLAMA_URL.split("/api/")[0]
    try:
        urllib.request.urlopen(f"{baza}/api/tags", timeout=5)
        return True
    except Exception:
        return False


def featherless():
    return os.environ.get("LLM_PROVIDER", "ollama").strip().lower() == "featherless"


def model_gati():
    """True nëse modeli që do përdoret është gati: Ollama lokal, ose Featherless me çelës dhe model."""
    if featherless():
        return bool(os.environ.get("FEATHERLESS_API_KEY") and os.environ.get("FEATHERLESS_MODEL"))
    return ollama_gati()


def pyet_ollama(prompt, si_json=False):
    """Thirrje te modeli (Ollama lokal ose, me LLM_PROVIDER=featherless, Featherless); kthen vetëm
    përgjigjen (pa <think>). si_json=True e detyron modelin të kthejë JSON të vlefshëm.
    Emri mbetet pyet_ollama, sepse extractor.py dhe perkthe() e thërrasin kështu."""
    if featherless():
        kerkesa = {"model": os.environ["FEATHERLESS_MODEL"], "temperature": 0, "max_tokens": 4096,
                   "messages": [{"role": "user", "content": prompt}]}
        if si_json:
            kerkesa["response_format"] = {"type": "json_object"}
        # Çelësi vetëm në header, kurrë në URL ose në log
        req = urllib.request.Request(FEATHERLESS_URL, data=json.dumps(kerkesa).encode(), headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {os.environ['FEATHERLESS_API_KEY']}"})
        lexo = lambda d: d["choices"][0]["message"]["content"]
    else:
        kerkesa = {"model": MODELI, "prompt": prompt, "stream": False,
                   "think": False, "options": {"temperature": 0}}
        if si_json:
            kerkesa["format"] = "json"
        req = urllib.request.Request(OLLAMA_URL, data=json.dumps(kerkesa).encode(),
                                     headers={"Content-Type": "application/json"})
        lexo = lambda d: d["response"]
    # Ollama ndonjëherë kthen 500 (p.sh. kur modeli ringarkohet), API-ja 429 (kufi ritmi); riprovo 2 herë
    for prova in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                pergjigja = lexo(json.loads(r.read()))
            break
        except urllib.error.HTTPError as e:
            if (e.code < 500 and e.code != 429) or prova == 2:
                raise
        except urllib.error.URLError:
            if prova == 2:
                raise
        time.sleep(5 * (prova + 1))
    # modelet "reasoning" ndonjëherë e shtojnë mendimin në tekst; hiqe
    return re.sub(r"<think>.*?</think>", "", pergjigja, flags=re.S).strip()


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


def kontrollo_llm():
    """Pa rrjet: zgjedhja e provider-it, kërkesa që dërgohet dhe leximi i përgjigjes, me API të simuluar."""
    import io
    from unittest.mock import patch
    derguar = []

    def pergjigje(req, timeout):
        derguar.append(req)
        d = ({"choices": [{"message": {"content": "<think>x</think> OK"}}]} if "chat/completions" in req.full_url
             else {"response": "OK"})
        return io.BytesIO(json.dumps(d).encode())

    with patch.dict(os.environ, {"LLM_PROVIDER": "", "FEATHERLESS_API_KEY": "sekret-prove"}), \
            patch("urllib.request.urlopen", pergjigje):
        assert pyet_ollama("p") == "OK" and derguar[-1].full_url == OLLAMA_URL  # parazgjedhja: lokal
    with patch.dict(os.environ, {"LLM_PROVIDER": "featherless", "FEATHERLESS_API_KEY": "sekret-prove",
                                 "FEATHERLESS_MODEL": "model-prove"}), patch("urllib.request.urlopen", pergjigje):
        assert model_gati() and pyet_ollama("p", si_json=True) == "OK"
        req = derguar[-1]
        trupi = json.loads(req.data)
        assert req.full_url == FEATHERLESS_URL and req.get_header("Authorization") == "Bearer sekret-prove"
        assert "sekret" not in req.full_url and trupi["model"] == "model-prove"
        assert trupi["response_format"] == {"type": "json_object"} and trupi["messages"][0]["content"] == "p"
    with patch.dict(os.environ, {"LLM_PROVIDER": "featherless", "FEATHERLESS_API_KEY": "", "FEATHERLESS_MODEL": "m"}):
        assert not model_gati()  # pa çelës s'niset
    print("Kontrollet e provider-it të modelit kaluan (pa rrjet).")


if __name__ == "__main__" and "--kontrollo" in sys.argv:
    kontrollo_llm()
elif __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    ok, gabime = perpuno(n)
    print(f"\nU përpunuan {ok}, gabime {gabime}.")
