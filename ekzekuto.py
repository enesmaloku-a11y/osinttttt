"""ekzekuto.py - Nis pipeline-in (main.py) një herë, me log dhe pa dy ekzekutime njëkohësisht.

Përdoret nga butoni "Ekzekuto tani" në dashboard dhe nga Windows Task Scheduler.
Nis me:  python ekzekuto.py 20      (deri në 20 artikuj për përkthim/nxjerrje)
"""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
import traceback
import warnings
from datetime import datetime

WINDOWS = os.name == "nt"
if WINDOWS:
    import msvcrt
else:  # Linux (p.sh. Streamlit Cloud): bllokimi me fcntl, pa Task Scheduler
    import fcntl

DOSJA = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(DOSJA, "pipeline.log")
LOCK = os.path.join(DOSJA, "pipeline.lock")
ORARI = os.path.join(DOSJA, "orari.json")
DETYRA = "OSINT Kosova"          # emri i detyrës në Task Scheduler
MAX_LOG = 1_000_000              # bajt; log-u i vjetër pritet që të mos rritet pa fund
PA_DRITARE = 0x08000000          # CREATE_NO_WINDOW: pa dritare konsole


# ---------------- Bllokimi: vetëm një ekzekutim në të njëjtën kohë ----------------
def _blloko(f):
    """Bllokon bajtin e parë të LOCK. Sistemi e liron vetë kur procesi mbyllet/rrëzohet.
    Kur bllokimi është i zënë ngre OSError (në Linux BlockingIOError, nënklasë e saj)."""
    f.seek(0)
    if WINDOWS:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def po_punon():
    """True nëse një ekzekutim tjetër e mban bllokimin tani."""
    with open(LOCK, "a+") as f:
        try:
            _blloko(f)
        except OSError:
            return True
        f.seek(0)
        if WINDOWS:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False


def ekzekuto(n, *, vetem_mbledhje=False):
    """Kalon një herë me bllokim të përbashkët dhe kthen kodin e daljes."""
    with contextlib.chdir(DOSJA), open(LOCK, "a+") as bllok:
        try:
            _blloko(bllok)
        except OSError:
            return 0  # procesi aktiv është pronari i logut
        if os.path.exists(LOG) and (madhesia := os.path.getsize(LOG)) > MAX_LOG:
            with open(LOG, "rb") as f:
                f.seek(madhesia - MAX_LOG // 2)
                fundi = f.read().decode("utf-8", errors="ignore")
            with open(LOG, "w", encoding="utf-8") as f:
                f.write(fundi)
        with (open(LOG, "a", encoding="utf-8", buffering=1) as log,
              contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), warnings.catch_warnings()):
            warnings.simplefilter("ignore")
            veprimi = "vetëm mbledhje" if vetem_mbledhje else f"deri në {n} artikuj"
            print(f"\n===== {datetime.now():%Y-%m-%d %H:%M} FILLIMI ({veprimi}) =====")
            kodi = 0
            try:
                if vetem_mbledhje:
                    import collector
                    from raporti import ngrire
                    if ngrire():
                        print("Pipeline-i është i ngrirë (etiketim): s'u bë asgjë.")
                    else:
                        print(collector.mblidh_te_gjitha())
                else:
                    import main
                    main.main(n)
            except SystemExit as e:  # p.sh. "Ollama nuk po punon"
                kodi = e.code if isinstance(e.code, int) else int(e.code is not None)
                if e.code is not None:
                    print(e)
            except Exception:
                kodi = 1
                traceback.print_exc()
            gjendja = "DËSHTOI" if kodi else "FUNDI"
            print(f"===== {datetime.now():%Y-%m-%d %H:%M} {gjendja} =====")
            return kodi


def nis_ne_sfond(n):
    """Nis ekzekuto.py si proces më vete, që të vazhdojë edhe kur dashboard-i rifreskohet."""
    subprocess.Popen([sys.executable, os.path.join(DOSJA, "ekzekuto.py"), str(n)],
                     cwd=DOSJA, creationflags=PA_DRITARE if WINDOWS else 0, close_fds=True)


def log_fundit(rreshta=25):
    if not os.path.exists(LOG):
        return "Ende s'ka asnjë ekzekutim."
    with open(LOG, encoding="utf-8", errors="ignore") as f:
        return "".join(f.readlines()[-rreshta:])


# ---------------- Orari automatik (Windows Task Scheduler) ----------------
def _schtasks(*args):
    if not WINDOWS:
        return False, "Orari automatik punon vetëm në Windows (Task Scheduler)."
    r = subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=PA_DRITARE)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def vendos_orarin(ore, n=20):
    """Krijon/zëvendëson detyrën që nis ekzekuto.py çdo 'ore' orë. Kthen (ok, mesazhi)."""
    # pythonw.exe nuk hap dritare konsole çdo orë
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    komanda = f'"{pythonw}" "{os.path.join(DOSJA, "ekzekuto.py")}" {int(n)}'
    orari = ["/SC", "DAILY"] if ore == 24 else ["/SC", "HOURLY", "/MO", str(int(ore))]
    ok, mesazhi = _schtasks("/Create", "/F", "/TN", DETYRA, "/TR", komanda, *orari)
    if ok:
        with open(ORARI, "w", encoding="utf-8") as f:
            json.dump({"ore": int(ore), "n": int(n)}, f)
    return ok, mesazhi


def hiq_orarin():
    """Fshin detyrën automatike (nëse ekziston)."""
    if not _schtasks("/Query", "/TN", DETYRA)[0]:
        return True, "S'kishte orar automatik."
    ok, mesazhi = _schtasks("/Delete", "/TN", DETYRA, "/F")
    if ok:
        with contextlib.suppress(FileNotFoundError):
            os.remove(ORARI)
    return ok, mesazhi


def orari_aktual():
    """Kthen {"ore", "n"} nëse detyra ekziston në Task Scheduler, përndryshe None."""
    if not (os.path.exists(ORARI) and _schtasks("/Query", "/TN", DETYRA)[0]):
        return None
    try:
        with open(ORARI, encoding="utf-8") as f:
            orari = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(orari, dict) or any(type(orari.get(k)) is not int or orari[k] < 1 for k in ("ore", "n")):
        return None
    return orari


def kontrollo():
    """Prova offline për ngrirjen, kodin e gabimit dhe konfigurimin e orarit."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    import collector
    import main
    with tempfile.TemporaryDirectory() as dosja:
        skedari = Path(dosja) / "pipeline.log"
        orari = Path(dosja) / "orari.json"
        with (patch.multiple(__name__, DOSJA=dosja, LOG=skedari, LOCK=Path(dosja) / "pipeline.lock", ORARI=orari),
              patch.dict(os.environ, {"OSINT_NGRIRE": "1"}), patch.object(collector, "mblidh_te_gjitha") as mblidh):
            assert ekzekuto(1, vetem_mbledhje=True) == 0
            mblidh.assert_not_called()
            with patch.object(main, "main", side_effect=SystemExit("gabim i provës")):
                assert ekzekuto(1) == 1
            assert "DËSHTOI" in skedari.read_text(encoding="utf-8")
            orari.write_text("[", encoding="utf-8")
            with patch(__name__ + "._schtasks", side_effect=[(True, ""), (True, ""), (False, "gabim")]):
                assert orari_aktual() is None
                assert not hiq_orarin()[0] and orari.exists()
    print("Kontrollet e ekzekutimit kaluan.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("n", type=int, nargs="?", default=20)
    parser.add_argument("--mbledhje", action="store_true", help="vetëm RSS/GDELT, pa model")
    parser.add_argument("--interval", type=int, help="përsërit çdo N sekonda")
    parser.add_argument("--kontrollo", action="store_true", help="provat offline")
    args = parser.parse_args()
    if args.kontrollo:
        kontrollo()
        sys.exit(0)
    if args.n < 1 or (args.interval is not None and args.interval < 1):
        parser.error("Numri i artikujve dhe intervali duhet të jenë pozitivë")
    while True:
        kodi = ekzekuto(args.n, vetem_mbledhje=args.mbledhje)
        if args.interval is None:
            sys.exit(kodi)
        time.sleep(args.interval)
