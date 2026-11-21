"""Veçoritë e provave të disponueshme në momentin e vlerësimit."""
import json
import re
from contextlib import closing
from datetime import datetime, timezone

import db

EMRAT = ("n_mediat", "n_gjuhet", "n_artikuj", "besueshmeria_mediave", "konflikte",
         "vend_i_sakte", "date_e_sakte", "burim_zyrtar", "ore_perhapje", "ka_rast_euvsdisinfo")
INSTITUCION = re.compile(r"\b(polic|policij|polici|kfor|eulex|ministr|prokuror|gjykat|court|prosecutor|sudstvo)", re.I)


def ore_perhapje(urls):
    if len(urls) < 2:
        return 0.0
    me_date = []
    with closing(db.lidhu()) as lidhja:
        for r in lidhja.execute("SELECT data FROM articles WHERE url IN (SELECT value FROM json_each(?))",
                                (json.dumps(urls),)):
            try:
                dita = datetime.fromisoformat(r[0].replace("Z", "+00:00"))
                me_date.append(dita if dita.tzinfo else dita.replace(tzinfo=timezone.utc))
            except (ValueError, AttributeError):
                continue
    if len(me_date) < 2:
        return 0.0
    return min(168.0, (max(me_date) - min(me_date)).total_seconds() / 3600)


def vektori(e) -> dict[str, float]:
    from scoring import pike_detajesh, pike_mediash

    e = dict(e)
    det = json.loads(e.get("detajet_json") or "{}")
    urls = set(json.loads(e.get("burimet") or "[]"))
    mediat = set(det.get("mediat") or [])
    gjuhet = set(det.get("gjuhet") or [])
    zyrtar = any(INSTITUCION.search(a) for a in det.get("aktoret") or [] if isinstance(a, str))
    rast = any(isinstance(k, dict) and k.get("burimi") == "EUvsDisinfo" and
               k.get("lloji") == "rast_i_ngjashem" for k in det.get("konteksti") or [])
    vlerat = (len(mediat), len(gjuhet), len(urls), pike_mediash(mediat) if mediat else 0,
              len(pike_detajesh(det, len(mediat))[1]), det.get("saktesia_vendit") in ("village", "municipality"),
              det.get("saktesia_dates") == "exact", zyrtar, ore_perhapje(sorted(urls)), rast)
    return dict(zip(EMRAT, map(float, vlerat), strict=True))


if __name__ == "__main__":
    assert not any(vektori({}).values())
    prove = {"mediat": ["RTK", "Koha"], "gjuhet": ["sq"], "aktoret": ["Kosovo Police"],
             "killed": [0, 2], "saktesia_dates": "exact", "saktesia_vendit": "village"}
    v = vektori({"detajet_json": json.dumps(prove), "burimet": '["a"]'})
    assert v["n_mediat"] == 2 and v["konflikte"] == v["burim_zyrtar"] == v["vend_i_sakte"] == 1
    print("Kontrollet e veçorive kaluan.")

