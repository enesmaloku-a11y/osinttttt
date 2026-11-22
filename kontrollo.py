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
    ("processor.py", ["processor.py", "--kontrollo"]),
    ("collector.py", ["collector.py", "--kontrollo"]),
    ("extractor.py", ["extractor.py", "0"]),
    ("correlator.py", ["correlator.py"]),
    ("scoring.py", ["scoring.py"]),
    ("trajno.py", ["trajno.py", "--kontrollo"]),
    ("patterns.py", ["patterns.py"]),
    ("vektori.py", ["vektori.py"]),
    ("kontekst_dezinformim.py", ["kontekst_dezinformim.py"]),
    ("kontekst_kibernetik.py", ["-c", "import kontekst_kibernetik as k; k.kontrollet()"]),
    ("eval/evaluate.py", ["-c", "import sys; sys.path.insert(0, 'eval'); import evaluate as e; "
                    "e.kontrollo(); e.lexo_gold()"]),
    ("kercenimet.py", ["kercenimet.py"]),
    ("rreziku.py", ["rreziku.py"]),
    ("apify_burimi.py", ["apify_burimi.py"]),
    ("raporti.py", ["raporti.py", "2026-11-18"]),
    # Me OSINT_NGRIRE=1 main() del para çdo hapi (as Ollama, as rrjet)
    ("main.py (ngrirja)", ["-c", "import os; os.environ['OSINT_NGRIRE'] = '1'; import main, processor; "
                          "processor.gabimi_modelit = lambda: (_ for _ in ()).throw(AssertionError('s u ngri')); "
                          "main.main(1)"]),
    ("ekzekuto.py", ["ekzekuto.py", "--kontrollo"]),
    ("demo.py", ["demo.py", "--kontrollo"]),
    ("demo_live.py", ["demo_live.py"]),
    ("dashboard.py", ["-c", "from streamlit.testing.v1 import AppTest; "
                         "at = AppTest.from_file('dashboard.py', default_timeout=90).run(); "
                         "assert not at.exception, [x.value for x in at.exception]"]),
    # Me fjalëkalim: pa e dhënë, faqja s'tregon asgjë përveç fushës së fjalëkalimit
    ("dashboard.py (fjalëkalimi)", ["-c", "import os; os.environ['OSINT_FJALEKALIMI'] = 'prove-123'; "
                                         "from streamlit.testing.v1 import AppTest; "
                                         "at = AppTest.from_file('dashboard.py', default_timeout=120).run(); "
                                         "assert not at.exception and not at.tabs and len(at.text_input) == 1; "
                                         "at.text_input[0].input('gabim').run(); assert not at.tabs and at.error; "
                                         "at.text_input[0].input('prove-123').run(); "
                                         "assert not at.exception and len(at.tabs) > 5, [x.value for x in at.exception]"]),
    # Railway: edhe me CLOUD=1, baza e konfiguruar s'duhet kaluar te demo.gjenero.
    ("dashboard.py (cloud me baze reale)", ["-c", "import os, tempfile, sqlite3; from pathlib import Path; "
                         "import db, demo; from streamlit.testing.v1 import AppTest; "
                         "tmp = tempfile.TemporaryDirectory(); "
                         "p = Path(tmp.name) / 'osint.db'; os.environ['OSINT_DB'] = str(p); "
                         "os.environ['OSINT_CLOUD'] = '1'; db.DB_PATH = str(p); "
                         "demo.gjenero = lambda *a: (_ for _ in ()).throw(AssertionError('demo mbi baze reale')); "
                         "at = AppTest.from_file('dashboard.py', default_timeout=90).run(); "
                         "assert not at.exception, [x.value for x in at.exception]; "
                         "assert Path(db.DB_PATH) == p and not db.ngjarjet(); "
                         "c = sqlite3.connect(p); c.execute('CREATE TABLE ruajtja (v TEXT)'); "
                         "c.execute(\"INSERT INTO ruajtja VALUES ('ruaje')\"); c.commit(); c.close(); "
                         "at.run(); assert not at.exception, [x.value for x in at.exception]; "
                         "c = sqlite3.connect(p); assert c.execute('SELECT v FROM ruajtja').fetchone()[0] == 'ruaje'; "
                         "c.close(); tmp.cleanup()"]),
    # Cloud pa OSINT_DB merr një demo të përkohshme vetëm për lexim.
    ("dashboard.py (cloud)", ["-c", "import os, db; from pathlib import Path; "
                                   "os.environ.pop('OSINT_DB'); os.environ['OSINT_CLOUD'] = '1'; "
                                   "from streamlit.testing.v1 import AppTest; "
                                   "at = AppTest.from_file('dashboard.py', default_timeout=120).run(); "
                                   "assert not at.exception, [x.value for x in at.exception]; "
                                   "b = [x for x in at.button if any(f in x.label for f in ('Ekzekuto', 'Mblidh lajmet', 'orarin'))]; "
                                   "assert len(b) == 3 and all(x.disabled for x in b), [(x.label, x.disabled) for x in b]; "
                                   "assert Path(db.DB_PATH).parent.name.startswith('osint-demo-'); "
                                   "assert not Path('demo.db').exists() and len(db.ngjarjet()) == 28; "
                                   "assert not any(x.label == 'Ruaj vendimin' for x in at.button)"]),
    # Demo + postimet sociale: data vetëm-ditë (gold) dhe me orë (Apify) bashkë; asnjë s'humbet te Artikujt
    ("dashboard.py (data të përziera)", ["-c", "import os, demo, apify_burimi, db; "
                                   "p = os.path.join(os.path.dirname(os.environ['OSINT_DB']), 'demo_sociale.db'); "
                                   "demo.gjenero(p); apify_burimi.demo(p); os.environ['OSINT_DB'] = db.DB_PATH = p; "
                                   "from streamlit.testing.v1 import AppTest; "
                                   "at = AppTest.from_file('dashboard.py', default_timeout=120).run(); "
                                   "assert not at.exception, [x.value for x in at.exception]; "
                                   "df = next(d.value for d in at.dataframe if {'burimi', 'titulli', 'publikimi'} <= set(d.value.columns)); "
                                   "s = df[df['burimi'].str.startswith('Reddit:')]; "
                                   "assert len(s) and (s['publikimi'] != '–').all() and df.index[0] in s.index, df.head(3)"]),
]


def main():
    deshtuan = []
    # Terminali i Windows (cp1252) s'i shtyp dot cirilikun e logjeve: zëvendësoje, mos u rrëzo
    sys.stdout.reconfigure(errors="replace")
    with tempfile.TemporaryDirectory() as tmp:
        kopja = Path(tmp) / "projekti"
        shutil.copytree(DOSJA, kopja, ignore=shutil.ignore_patterns(
            "venv", ".venv", ".git", "*.db", "data", "__pycache__", "pipeline.*", "orari.json"))
        env = {**os.environ, "OSINT_DB": str(Path(tmp) / "kontroll.db"), "PYTHONWARNINGS": "ignore",
               "PYTHONIOENCODING": "utf-8"}  # fëmijët shkruajnë UTF-8, pavarësisht terminalit
        for emri, komanda in KONTROLLET:
            if not (kopja / emri.split()[0]).exists():
                print(f"  -   {emri} (s'ekziston në këtë degë)")
                continue
            try:
                r = subprocess.run([sys.executable, *komanda], cwd=kopja, env=env,
                                   capture_output=True, encoding="utf-8", errors="replace", timeout=300)
            except subprocess.TimeoutExpired:
                deshtuan.append(emri)
                print(f"  GABIM {emri} (kaloi kufirin prej 300 sekondash)")
                continue
            ok = r.returncode == 0
            print(f"  {'OK ' if ok else 'GABIM'} {emri}")
            if not ok:
                deshtuan.append(emri)
                print("      " + (r.stderr or r.stdout).strip().replace("\n", "\n      ")[-1500:])
    print("Të gjitha kontrollet kaluan." if not deshtuan else f"Dështuan: {', '.join(deshtuan)}")
    return 1 if deshtuan else 0


if __name__ == "__main__":
    sys.exit(main())
