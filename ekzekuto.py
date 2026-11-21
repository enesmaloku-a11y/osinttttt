"""ekzekuto.py - Nis pipeline-in (main.py) një herë, me log dhe pa dy ekzekutime njëkohësisht.

Përdoret nga butoni "Ekzekuto tani" në dashboard dhe nga Windows Task Scheduler.
Nis me:  python ekzekuto.py 20      (deri në 20 artikuj për përkthim/nxjerrje)
"""
import contextlib
import json
import os
import subprocess
import sys
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


def ekzekuto(n):
    """Kalon main.py një herë dhe shkruan gjithçka te pipeline.log."""
    os.chdir(DOSJA)  # Task Scheduler e nis nga System32; baza osint.db është këtu
    sys.path.insert(0, DOSJA)
    if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG:
        with open(LOG, encoding="utf-8", errors="ignore") as f:
            fundi = f.read()[-MAX_LOG // 2:]
        with open(LOG, "w", encoding="utf-8") as f:
            f.write(fundi)

    with open(LOCK, "a+") as bllok, open(LOG, "a", encoding="utf-8", buffering=1) as log:
        try:
            _blloko(bllok)
        except OSError:
            log.write(f"{datetime.now():%Y-%m-%d %H:%M} një ekzekutim tjetër po punon; u anashkalua.\n")
            return
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            warnings.simplefilter("ignore")  # paralajmërimet e librarive s'i duhen analistit
            print(f"\n===== {datetime.now():%Y-%m-%d %H:%M} FILLIMI (deri në {n} artikuj) =====")
            try:
                import main
                main.main(n)
            except SystemExit as e:  # p.sh. "Ollama nuk po punon"
                print(e)
            except Exception:
                traceback.print_exc()
            print(f"===== {datetime.now():%Y-%m-%d %H:%M} FUNDI =====")


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
    if os.path.exists(ORARI):
        os.remove(ORARI)
    if not _schtasks("/Query", "/TN", DETYRA)[0]:
        return True, "S'kishte orar automatik."
    return _schtasks("/Delete", "/TN", DETYRA, "/F")


def orari_aktual():
    """Kthen {"ore", "n"} nëse detyra ekziston në Task Scheduler, përndryshe None."""
    if not (os.path.exists(ORARI) and _schtasks("/Query", "/TN", DETYRA)[0]):
        return None
    with open(ORARI, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    ekzekuto(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
