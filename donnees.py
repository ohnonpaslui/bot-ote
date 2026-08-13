"""
donnees.py — Bougies journalieres, gratuitement et sans compte.

Yahoo publie l'historique quotidien de la plupart des futures, indices,
paires de devises et cryptos. On demande explicitement `range=max` puis
`range=25y` et on garde la serie la plus longue : sur les contrats a terme,
« max » renvoie parfois 266 jours la ou « 25y » en renvoie 5 000. Le mot ne
veut pas dire ce qu'il annonce, et s'y fier a deja fausse un test entier.

Le cache evite de retelecharger a chaque cycle. Il est volontairement place
hors du depot : ce sont des donnees publiques, pas du code.
"""

import json
import os
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
ENTETES = {"User-Agent": "Mozilla/5.0"}
MIN_BOUGIES = 800          # en dessous, la structure n'a pas de quoi se former


def journalier(symbole, essais=2):
    """Historique quotidien, ou None si le symbole est indisponible."""
    os.makedirs(CACHE, exist_ok=True)
    chemin = os.path.join(
        CACHE, symbole.replace("=", "").replace("^", "").replace("-", "")
        + ".parquet")

    frais = None
    if os.path.exists(chemin):
        age = time.time() - os.path.getmtime(chemin)
        if age < 12 * 3600:                    # deja rafraichi aujourd'hui
            return pd.read_parquet(chemin)
        frais = pd.read_parquet(chemin)

    meilleur = None
    for plage in ("max", "25y"):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(symbole)}?interval=1d&range={plage}")
        for _ in range(essais):
            try:
                req = urllib.request.Request(url, headers=ENTETES)
                brut = json.loads(urllib.request.urlopen(req, timeout=45).read())
                break
            except Exception:
                time.sleep(1.5)
        else:
            continue
        res = (brut.get("chart") or {}).get("result")
        if not res or not res[0].get("timestamp"):
            continue
        q = res[0]["indicators"]["quote"][0]
        d = pd.DataFrame({
            "ouv_ms": np.array(res[0]["timestamp"], dtype="int64") * 1000,
            "open": q["open"], "high": q["high"],
            "low": q["low"], "close": q["close"],
            "volume": q.get("volume") or [0] * len(res[0]["timestamp"]),
        }).dropna(subset=["open", "high", "low", "close"])
        if meilleur is None or len(d) > len(meilleur):
            meilleur = d
        time.sleep(0.25)

    if meilleur is None or len(meilleur) < MIN_BOUGIES:
        # Une panne reseau ne doit pas faire disparaitre un instrument du
        # portefeuille : on retombe sur le cache s'il existe.
        return frais
    meilleur = (meilleur.drop_duplicates("ouv_ms").sort_values("ouv_ms")
                .reset_index(drop=True))
    meilleur.to_parquet(chemin, index=False)
    return meilleur
