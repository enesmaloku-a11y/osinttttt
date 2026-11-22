"""main.py - Kalon gjithë pipeline-in me një komandë.

Nis me:  python main.py        (deri në 20 artikuj për përkthim dhe nxjerrje)
         python main.py 50     (deri në 50)
Pastaj:  streamlit run dashboard.py

Artikujt që s'arrihen në këtë ekzekutim përpunohen herën tjetër (cache në SQLite).
Radha: mbledhja -> përkthimi -> nxjerrja -> korrelimi -> konteksti -> besueshmëria -> rreziku
-> alarmet -> raporti ditor. Konteksti vjen para besueshmërisë, që scoring.py ta ruajë te
detajet; rreziku vjen pas saj, sepse prioriteti kërkon besueshmërinë.
"""
import importlib
import sys
import time

import collector
import correlator
import db
import extractor
import patterns
import processor
import scoring
from raporti import ngrire


def opsional(emri, funksioni):
    """Thërret emri.funksioni() nëse moduli ekziston. Gabimi i tij s'e ndal pipeline-in."""
    try:
        moduli = importlib.import_module(emri)
    except ModuleNotFoundError as e:
        if e.name != emri:  # moduli ekziston, por i mungon një varësi: thuaje
            print(f"  {emri}: mungon varësia {e.name}, u anashkalua")
        return None
    try:
        return getattr(moduli, funksioni)()
    except Exception as e:
        print(f"  {emri}: gabim ({type(e).__name__}: {e}), u anashkalua")
        return None


def main(n):
    # Ngrirja gjatë etiketimit: as Task Scheduler-i as një terminal tjetër s'e nis pipeline-in
    if ngrire():
        print("Pipeline-i është i ngrirë (etiketim): s'u bë asgjë.")
        return
    # Kontrollo para mbledhjes, që të mos presim për asgjë nëse modeli s'punon
    if not processor.model_gati():
        sys.exit("Modeli s'është gati: nis Ollama ('ollama serve'), ose me LLM_PROVIDER=featherless "
                 "vendos FEATHERLESS_API_KEY dhe FEATHERLESS_MODEL.")
    t0 = time.time()

    print("1/7 Mbledhja e artikujve...")
    te_reja = sum(collector.mblidh_te_gjitha().values())

    print(f"\n2/7 Përkthimi në anglisht (deri në {n} artikuj)...")
    perkthyer, gabime_p = processor.perpuno(n)

    print(f"\n3/7 Nxjerrja e ngjarjeve (deri në {n} artikuj)...")
    me_model, filtruar, gabime_n, ngjarje = extractor.perpuno(n)

    print("\n4/7 Korrelimi i artikujve në ngjarje...")
    grupe = correlator.korrelo()

    print("5/7 Konteksti i jashtëm (EUvsDisinfo, EuRepoC)...")
    for emri in ("kontekst_dezinformim", "kontekst_kibernetik"):
        k = opsional(emri, "pasuro_te_gjitha")
        if k is not None:
            print(f"  {emri}: {k} ngjarje me kontekst")

    print("6/7 Besueshmëria...")
    scoring.vlereso_te_gjitha()

    print("7/7 Rreziku dhe prioriteti...")
    r = opsional("rreziku", "vlereso_te_gjitha")
    print(f"  {r} ngjarje të vlerësuara" if r is not None else "  rreziku.py mungon, u anashkalua")

    # Alarmet për rritje të pazakonta (vetëm informim; analisti vendos)
    alarmet = patterns.rritjet(db.ngjarjet(), fillimi_mbledhjes=db.fillimi_i_mbledhjes())
    for a in alarmet:
        print("  ALARM: " + patterns.pershkrim(a))

    raporti = opsional("raporti", "gjenero")
    print(f"\nGati për {time.time() - t0:.0f} s: {te_reja} artikuj të rinj, {perkthyer} të përkthyer, "
          f"{me_model} kaluan te modeli ({ngjarje} ngjarje sigurie), {filtruar} u filtruan pa model, "
          f"{gabime_p + gabime_n} gabime. Gjithsej {grupe} ngjarje në bazë.")
    if raporti:
        print(f"Raporti ditor: {raporti}")
    print("Hap dashboard-in me:  streamlit run dashboard.py")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
