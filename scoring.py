"""scoring.py - Besueshmëria e ngjarjeve me rregulla të qarta (JO nga modeli).

besueshmëria = 0.40 * burimet e pavarura
             + 0.35 * besueshmëria e mediave
             + 0.25 * përputhja e detajeve
Çdo pjesë është 0..1, dhe arsyetimi ruhet që analisti ta shohë.
"""
import json

import db

PESHAT = {"burimet": 0.40, "mediat": 0.35, "detajet": 0.25}

# Besueshmëria e mediave (0..1). Vlerë fillestare: duhet ta caktojë/rishikojë analisti.
MEDIAT = {
    "Balkan Insight": 0.9, "Kallxo": 0.85, "RTK": 0.8, "Koha": 0.8, "N1 Serbia": 0.8,
    "Telegrafi": 0.6, "Gazeta Express": 0.6,
}
E_PANJOHUR = 0.4  # çdo domen tjetër nga GDELT


def pike_burimesh(mediat, gjuhet):
    """1 medium = 0.33, 2 = 0.67, 3+ = 1.0. Bonus nëse raportojnë media në gjuhë të ndryshme."""
    p = min(len(mediat), 3) / 3
    if len(gjuhet) > 1:
        p = min(1.0, p + 0.15)
    return p


def pike_mediash(mediat):
    """Mesatarja e besueshmërisë së mediave që raportojnë."""
    return sum(MEDIAT.get(m, E_PANJOHUR) for m in mediat) / len(mediat)


def pike_detajesh(det, n_burime):
    """1.0 kur detajet përputhen; -0.3 për çdo numër kontradiktor.
    Me një burim të vetëm s'ka çfarë të krahasohet -> 0.5."""
    if n_burime < 2:
        return 0.5, []
    konflikte = [k for k in ("killed", "injured", "arrested")
                 if len({v for v in det.get(k, []) if v is not None}) > 1]
    return max(0.0, 1.0 - 0.3 * len(konflikte)), konflikte


def vlereso(det):
    """Kthen (besueshmëria 0..1, lista e arsyeve) për detajet e një ngjarjeje."""
    mediat = det.get("mediat") or []
    if not mediat:
        return 0.0, ["s'ka burime"]
    gjuhet = det.get("gjuhet") or []
    b = pike_burimesh(mediat, gjuhet)
    m = pike_mediash(mediat)
    d, konflikte = pike_detajesh(det, len(mediat))
    pike = round(PESHAT["burimet"] * b + PESHAT["mediat"] * m + PESHAT["detajet"] * d, 2)
    arsyet = [
        f"burime të pavarura: {len(mediat)} ({', '.join(mediat)}), gjuhë: {len(gjuhet)} -> {b:.2f}",
        f"besueshmëria e mediave -> {m:.2f}",
        ("detajet: s'mund të krahasohen (një burim)" if len(mediat) < 2 else
         f"detajet: {'kontradikta te ' + ', '.join(konflikte) if konflikte else 'përputhen'}")
        + f" -> {d:.2f}",
    ]
    return pike, arsyet


def vlereso_te_gjitha():
    """Llogarit besueshmërinë për çdo ngjarje në bazë. Kthen numrin e ngjarjeve."""
    ngjarjet = db.ngjarjet()
    for e in ngjarjet:
        det = json.loads(e["detajet_json"] or "{}")
        pike, arsyet = vlereso(det)
        det["arsyetimi"] = arsyet
        db.ruaj_besueshmerine(e["id"], pike, det)
    return len(ngjarjet)


if __name__ == "__main__":
    # Kontrolle të vogla: më shumë burime/gjuhë => më e besueshme; kontradiktat ulin
    nje, _ = vlereso({"mediat": ["Telegrafi"], "gjuhet": ["sq"]})
    tre, _ = vlereso({"mediat": ["Koha", "N1 Serbia", "Balkan Insight"], "gjuhet": ["sq", "sr", "en"],
                      "killed": [1, 1, 1]})
    kontra, _ = vlereso({"mediat": ["Koha", "N1 Serbia"], "gjuhet": ["sq", "sr"], "killed": [1, 3]})
    pajtim, _ = vlereso({"mediat": ["Koha", "N1 Serbia"], "gjuhet": ["sq", "sr"], "killed": [1, 1]})
    assert nje < pajtim < tre and kontra < pajtim, (nje, kontra, pajtim, tre)
    print(f"Shembuj: 1 burim {nje}, 2 burime me kontradiktë {kontra}, 2 në pajtim {pajtim}, 3 burime {tre}")
    print(f"U vlerësuan {vlereso_te_gjitha()} ngjarje.")
