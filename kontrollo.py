"""kontrollo.py - Kalon kontrollet e çdo moduli (pa Ollama, pa rrjet) në një dosje të përkohshme.

Nis me:  python kontrollo.py
osint.db dhe data/ nuk preken: çdo kontroll punon në një kopje të projektit me OSINT_DB të vet.
Kthen kodin 1 nëse ndonjë kontroll dështon.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DOSJA = Path(__file__).resolve().parent

# (skedari i modulit, argumentet për python). Modulet që mungojnë në këtë degë anashkalohen.
KONTROLLET = [
    ("db.py", ["db.py"]),
    ("collector.py", ["collector.py", "--kontrollo"]),
    ("extractor.py", ["extractor.py", "0"]),
    ("correlator.py", ["correlator.py"]),
    ("scoring.py", ["scoring.py"]),
    ("patterns.py", ["patterns.py"]),
    ("vektori.py", ["vektori.py"]),
    ("kontekst_dezinformim.py", ["kontekst_dezinformim.py"]),
    ("kontekst_kibernetik.py", ["-c", "import kontekst_kibernetik as k; k.kontrollet()"]),
    ("eval/evaluate.py", ["-c", "import sys; sys.path.insert(0, 'eval'); import evaluate as e; "
                    "getattr(e, 'kontrollo', lambda: None)(); e.lexo_gold()"]),
    ("kercenimet.py", ["kercenimet.py"]),
    ("rreziku.py", ["rreziku.py"]),
    ("apify_burimi.py", ["apify_burimi.py"]),
    ("raporti.py", ["raporti.py", "2026-11-18"]),
    # Me OSINT_NGRIRE=1 main() del para çdo hapi (as Ollama, as rrjet)
    ("main.py (ngrirja)", ["-c", "import os; os.environ['OSINT_NGRIRE'] = '1'; import main, processor; "
                          "processor.ollama_gati = lambda: (_ for _ in ()).throw(AssertionError('s u ngri')); "
                          "main.main(1)"]),
    ("demo.py", ["demo.py", "--kontrollo"]),
    ("dashboard.py", ["-c", "from streamlit.testing.v1 import AppTest; "
                         "at = AppTest.from_file('dashboard.py', default_timeout=90).run(); "
                         "assert not at.exception, [x.value for x in at.exception]"]),
    # Si në Streamlit Cloud: pa OSINT_DB krijon vetë demo.db, dhe s'lejon nisjen e pipeline-it
    ("dashboard.py (cloud)", ["-c", "import os, sqlite3; os.environ.pop('OSINT_DB'); os.environ['OSINT_CLOUD'] = '1'; "
                                   "from streamlit.testing.v1 import AppTest; "
                                   "at = AppTest.from_file('dashboard.py', default_timeout=120).run(); "
                                   "assert not at.exception, [x.value for x in at.exception]; "
                                   "b = [x for x in at.button if any(f in x.label for f in ('Ekzekuto', 'Mblidh lajmet', 'orarin'))]; "
                                   "assert len(b) == 3 and all(x.disabled for x in b), [(x.label, x.disabled) for x in b]; "
                                   "n = sqlite3.connect('demo.db').execute('SELECT COUNT(*) FROM articles').fetchone()[0]; "
                                   "assert n > 0 and len(at.expander) > 0, (n, len(at.expander))"]),
]


def main():
    deshtuan = []
    # Terminali i Windows (cp1252) s'i shtyp dot cirilikun e logjeve: zëvendësoje, mos u rrëzo
    sys.stdout.reconfigure(errors="replace")
    with tempfile.TemporaryDirectory() as tmp:
        kopja = Path(tmp) / "projekti"
        shutil.copytree(DOSJA, kopja, ignore=shutil.ignore_patterns(
            "venv", ".git", "*.db", "data", "__pycache__", "pipeline.*", "orari.json"))
        env = {**os.environ, "OSINT_DB": str(Path(tmp) / "kontroll.db"), "PYTHONWARNINGS": "ignore",
               "PYTHONIOENCODING": "utf-8"}  # fëmijët shkruajnë UTF-8, pavarësisht terminalit
        for emri, komanda in KONTROLLET:
            if not (kopja / emri.split()[0]).exists():
                print(f"  -   {emri} (s'ekziston në këtë degë)")
                continue
            r = subprocess.run([sys.executable, *komanda], cwd=kopja, env=env,
                               capture_output=True, encoding="utf-8", errors="replace", timeout=300)
            ok = r.returncode == 0
            print(f"  {'OK ' if ok else 'GABIM'} {emri}")
            if not ok:
                deshtuan.append(emri)
                print("      " + (r.stderr or r.stdout).strip().replace("\n", "\n      ")[-1500:])
    print("Të gjitha kontrollet kaluan." if not deshtuan else f"Dështuan: {', '.join(deshtuan)}")
    return 1 if deshtuan else 0


if __name__ == "__main__":
    sys.exit(main())
