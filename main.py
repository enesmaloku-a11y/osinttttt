"""main.py - Kalon gjithë pipeline-in me një komandë.

Nis me:  python main.py        (deri në 20 artikuj për përkthim dhe nxjerrje)
         python main.py 50     (deri në 50)
Pastaj:  streamlit run dashboard.py

Artikujt që s'arrihen në këtë ekzekutim përpunohen herën tjetër (cache në SQLite).
"""
import sys
import time

import collector
import correlator
import db
import extractor
import patterns
import processor
import scoring


def main(n):
    # Kontrollo para mbledhjes, që të mos presim për asgjë nëse modeli s'punon
    if not processor.ollama_gati():
        sys.exit("Ollama nuk po punon. Nise me 'ollama serve' dhe provo përsëri.")
    t0 = time.time()

    print("1/5 Mbledhja e artikujve...")
    te_reja = sum(collector.mblidh_te_gjitha().values())

    print(f"\n2/5 Përkthimi në anglisht (deri në {n} artikuj)...")
    perkthyer, gabime_p = processor.perpuno(n)

    print(f"\n3/5 Nxjerrja e ngjarjeve (deri në {n} artikuj)...")
    me_model, filtruar, gabime_n, ngjarje = extractor.perpuno(n)

    print("\n4/5 Korrelimi i artikujve në ngjarje...")
    grupe = correlator.korrelo()

    print("5/5 Besueshmëria...")
    scoring.vlereso_te_gjitha()

    # Alarmet për rritje të pazakonta (vetëm informim; analisti vendos)
    alarmet = patterns.rritjet(db.ngjarjet(), fillimi_mbledhjes=db.fillimi_i_mbledhjes())
    for a in alarmet:
        print("  ALARM: " + patterns.pershkrim(a))

    print(f"\nGati për {time.time() - t0:.0f} s: {te_reja} artikuj të rinj, {perkthyer} të përkthyer, "
          f"{me_model} kaluan te modeli ({ngjarje} ngjarje sigurie), {filtruar} u filtruan pa model, "
          f"{gabime_p + gabime_n} gabime. Gjithsej {grupe} ngjarje në bazë.")
    print("Hap dashboard-in me:  streamlit run dashboard.py")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
