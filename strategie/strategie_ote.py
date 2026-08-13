"""
strategie_ote.py — La strategie complete, telle que specifiee.

LA SEQUENCE, DANS L'ORDRE

  1. TENDANCE      structure haussiere ou baissiere. En range, on ne fait rien.
  2. JAMBE         le dernier creux confirme qui precede le dernier sommet
                   confirme. 0 au bout de l'impulsion, 1 a son origine.
  3. ZONE OTE      entre 0,618 et 0,786. Elle AUTORISE, elle ne declenche pas.
  4. CONFLUENCE    FVG, desequilibre de volume, bloc d'ordres ou cassure-retest,
                   situe DANS la zone. C'est lui qui declenche.
  5. ENTREE        au bord de la confluence que le prix atteint en premier.
  6. STOP          au niveau 1 du Fibonacci — le plus loin, a l'origine de
                   l'impulsion.
  7. OBJECTIF      au niveau 0 — le sommet de l'impulsion.
  8. SUIVEUR       on remonte le stop quand le trade avance.

LE RATIO EST IMPOSE PAR LA GEOMETRIE

  entree a 0,618  ->  risque 0,382 A, gain 0,618 A  ->  RR 1,62
  entree a 0,786  ->  risque 0,214 A, gain 0,786 A  ->  RR 3,67

Personne ne le choisit : il decoule de l'endroit ou se trouve la confluence.
C'est un degre de liberte en moins, donc une facon de moins de se tromper.

CE QUE LE SUIVEUR PEUT COUTER

Remonter le stop trop tot ampute l'esperance : le prix respire, revient sur
son point d'entree, et sort la position a zero avant de repartir. C'est
l'erreur de gestion la plus repandue. On teste donc quatre versions, dont
« aucun suiveur », et on laisse la mesure trancher.

CHRONOLOGIE

Aucune decision n'utilise la bougie en cours autrement que par ses extremes
deja franchis. Un pivot n'est utilise qu'a partir de sa confirmation. Une
confluence detectee a la bougie k n'est utilisable qu'a partir de k+1.
"""

import math
import statistics

import numpy as np
import pandas as pd

from . import confluences as CF
from . import structure as ST

ATTENTE_MAX = 60        # bougies pendant lesquelles la zone reste valable
DUREE_MAX = 200         # bougies avant de solder une position ouverte

SUIVEURS = ["aucun", "seuil 1R", "structure", "niveaux fib"]


def _stop_suiveur(mode, pos, i, df, struct, fib):
    """
    Nouveau stop, ou None si on ne bouge pas.

    On ne DESCEND jamais un stop : une fois remonte, il reste. Autoriser le
    contraire reviendrait a elargir le risque en cours de route, ce qui rend
    tout calcul de R faux.
    """
    s, e, sl = pos["s"], pos["e"], pos["sl"]
    cl = df["close"].values[i]
    gain = (cl - e) * s
    risque = abs(e - pos["sl_initial"])
    if risque <= 0:
        return None

    if mode == "seuil 1R":
        # au-dela d'un R de gain, le stop passe au point d'entree
        if gain >= risque:
            nouveau = e
        else:
            return None

    elif mode == "structure":
        # on suit le dernier creux confirme (ou sommet, en vente)
        if s > 0:
            ref = struct["dernier_bas"].iloc[i]
            if not np.isfinite(ref) or ref <= sl or ref >= cl:
                return None
            nouveau = ref
        else:
            ref = struct["dernier_haut"].iloc[i]
            if not np.isfinite(ref) or ref >= sl or ref <= cl:
                return None
            nouveau = ref

    elif mode == "niveaux fib":
        # chaque niveau franchi tire le stop au niveau precedent
        paliers = [(fib[0.0], fib[0.5]), (fib[0.5], fib[0.618]),
                   (fib[0.618], fib[0.786])]
        nouveau = None
        for atteint, vers in paliers:
            if (cl - atteint) * s >= 0:
                nouveau = vers
                break
        if nouveau is None:
            return None
    else:
        return None

    if (nouveau - sl) * s <= 0:          # jamais reculer
        return None
    return nouveau


def rejouer(df, suiveur="aucun", types_confluence=None, exiger_confluence=True):
    """
    Rejoue la strategie. Une position a la fois.

    `exiger_confluence=False` reproduit l'ancienne version — entree au simple
    contact de la zone. C'est le temoin qui permettra de chiffrer ce que la
    confluence apporte reellement.
    """
    struct = ST.tendance(df)
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    amp_moy = pd.Series(hi - lo).rolling(20).mean().values

    out, pos, attente = [], None, None
    derniere_jambe = None

    for i in range(ST.PIVOT_N + 25, len(df)):
        # ---------------- position ouverte ----------------
        if pos:
            if pos["s"] > 0:
                touche_sl, touche_tp = lo[i] <= pos["sl"], hi[i] >= pos["tp"]
            else:
                touche_sl, touche_tp = hi[i] >= pos["sl"], lo[i] <= pos["tp"]
            if (touche_sl or touche_tp) and i > pos["i"]:
                gain = ((pos["sl"] if touche_sl else pos["tp"]) - pos["e"]) * pos["s"]
                out.append({"r": gain / pos["risque"], "rr": pos["rr"],
                            "stop_bps": pos["stop_bps"],
                            "barres": i - pos["i"],
                            "issue": "sl" if touche_sl else "tp"})
                pos = None
            elif i - pos["i"] >= DUREE_MAX:
                gain = (cl[i] - pos["e"]) * pos["s"]
                out.append({"r": gain / pos["risque"], "rr": pos["rr"],
                            "stop_bps": pos["stop_bps"],
                            "barres": i - pos["i"], "issue": "duree"})
                pos = None
            else:
                n = _stop_suiveur(suiveur, pos, i, df, struct, pos["fib"])
                if n is not None:
                    pos["sl"] = n

        # ---------------- la zone en attente ----------------
        if pos is None and attente:
            s = attente["s"]
            # le prix entre-t-il dans la zone ?
            touche = (lo[i] <= attente["haut"] and hi[i] >= attente["bas"])
            trop_loin = (lo[i] < attente["fib"][1.0]) if s > 0 else \
                        (hi[i] > attente["fib"][1.0])
            if trop_loin:
                attente = None                    # jambe invalidee
            elif struct["tendance"].iloc[i] != s:
                # BUG CORRIGE — la structure a bascule entre le moment ou la
                # zone a ete dessinee et celui ou le prix y revient. L'audit
                # comptait 75 trades sur 159 pris a contresens : la tendance
                # etait verifiee au dessin, jamais a l'entree. Or la premiere
                # regle est justement de ne trader que dans le sens de la
                # structure — au moment ou l'on trade.
                attente = None
            elif touche:
                conf = CF.trouver(df, i - 1, s, attente["bas"], attente["haut"],
                                  types_confluence,
                                  min_taille=0.1 * (amp_moy[i - 1] or 0))
                if conf or not exiger_confluence:
                    if conf:
                        # BUG CORRIGE — un objet peut CHEVAUCHER la zone tout
                        # en ayant son bord au-dehors. Prendre ce bord faisait
                        # entrer hors de la zone OTE dans 26 % des cas, et
                        # cassait du meme coup la geometrie du ratio. On borne
                        # donc le niveau aux limites de la zone.
                        niveaux = [v[0] for v in conf.values() if v[0] is not None]
                        niveaux = [min(max(n, attente["bas"]), attente["haut"])
                                   for n in niveaux]
                        e = (min(niveaux) if s > 0 else max(niveaux)) if niveaux else None
                    else:
                        e = attente["haut"] if s > 0 else attente["bas"]
                    atteint = (lo[i] <= e) if s > 0 else (hi[i] >= e)
                    if e is not None and atteint:
                        sl, tp = attente["fib"][1.0], attente["fib"][0.0]
                        risque = abs(e - sl)
                        gain = abs(tp - e)
                        if risque > 0 and gain > 0:
                            pos = {"s": s, "i": i, "e": e, "sl": sl,
                                   "sl_initial": sl, "tp": tp, "risque": risque,
                                   "rr": gain / risque,
                                   "stop_bps": risque / e * 10_000,
                                   "fib": attente["fib"],
                                   "n_conf": sum(v[1] for v in conf.values())}
                            attente = None
            elif i - attente["i"] >= ATTENTE_MAX:
                attente = None

        # ---------------- armement d'une nouvelle zone ----------------
        if pos is not None or attente is not None:
            continue
        j = ST.jambe(struct, i)
        if j is None:
            continue
        origine, extremite, s = j
        if (struct["i_bas"].iloc[i], struct["i_haut"].iloc[i]) == derniere_jambe:
            continue
        derniere_jambe = (struct["i_bas"].iloc[i], struct["i_haut"].iloc[i])

        fib = ST.niveaux_fib(origine, extremite)
        bas, haut = ST.zone_ote(origine, extremite)
        # si le prix est deja dans la zone ou au-dela, la jambe est perimee
        if (cl[i] <= haut) if s > 0 else (cl[i] >= bas):
            continue
        attente = {"s": s, "bas": bas, "haut": haut, "fib": fib, "i": i}

    return out


def evaluer(trades, frais_bps):
    if len(trades) < 30:
        return None
    nets = [t["r"] - frais_bps / t["stop_bps"] for t in trades]
    m = statistics.fmean(nets)
    sd = statistics.pstdev(nets) or 1e-9
    return {"n": len(trades),
            "wr": sum(1 for t in trades if t["r"] > 0) / len(trades),
            "rr": statistics.median(t["rr"] for t in trades),
            "brut": statistics.fmean(t["r"] for t in trades),
            "net": m, "t": m * math.sqrt(len(trades)) / sd,
            "stop": statistics.median(t["stop_bps"] for t in trades),
            "duree": statistics.median(t["barres"] for t in trades)}
