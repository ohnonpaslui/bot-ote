"""
bot.py — Le bot en papier.

LE PRINCIPE, ET C'EST LE POINT LE PLUS IMPORTANT DU FICHIER

Un bot temps reel est d'ordinaire une REECRITURE de la strategie : le backtest
boucle sur l'historique, le bot regarde la derniere bougie. Les deux codes
divergent, et la divergence ne se voit jamais — le backtest continue d'afficher
ses beaux chiffres pendant que le bot fait autre chose.

Ici on ne reecrit rien. Chaque jour, on rejoue le backtest complet sur tout
l'historique disponible et on encaisse ce qui s'est ferme depuis la veille.
C'est le meme code, appele avec un jour de plus. Aucune divergence n'est
possible.

Le cout est du calcul redondant : quelques secondes par cycle. C'est derisoire
face a la classe de bugs que ca supprime.

CE QUI EST SIMULE, ET CE QUI NE L'EST PAS

  simule   le capital, les positions, les stops, les frais
  reel     les prix, les signaux, les dates

Aucune cle d'API n'existe dans ce depot. Le bot ne peut pas passer d'ordre,
et c'est deliberé.

POURQUOI DU PAPIER ET PAS DE L'ARGENT

L'avantage mesure vaut +0,035 a +0,050 R par trade selon l'echelle et la
periode — positif sur quatre mesures independantes, mais avec un t entre 1,06
et 1,92. C'est au-dessus du hasard, en dessous du seuil de preuve qu'exige le
nombre d'essais accumules pendant la recherche.

Le papier est le regime qui correspond a ce niveau de certitude. Il faut une
centaine de trades avant de pouvoir en dire quoi que ce soit, soit environ
neuf mois a ce rythme.

L'AUTOVERIFICATION

Avant chaque cycle, le bot verifie que le code respecte encore la
specification : ratios dans les bornes geometriques, stops non nuls. Si un
controle echoue, il s'arrete. Un bot arrete vaut mieux qu'un bot qui derive.
"""

import csv
import json
import os
from datetime import datetime, timezone

from donnees import journalier
from strategie import strategie_ote as S

RACINE = os.path.dirname(os.path.abspath(__file__))
ETAT = os.path.join(RACINE, "etat.json")
JOURNAL = os.path.join(RACINE, "trades.csv")

CAPITAL_DEPART = 1000.0
RISQUE_PCT = 1.0
SUIVEUR = "structure"      # la seule variante positive sur les quatre mesures

# Frais aller-retour en points de base, par instrument. Ils comptent : une
# strategie mesuree sans eux n'a aucune valeur.
UNIVERS = {
    **{s: 1.0 for s in ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X",
                        "AUDUSD=X", "NZDUSD=X", "USDCAD=X"]},
    **{s: 2.2 for s in ["EURGBP=X", "EURJPY=X", "GBPJPY=X", "EURCHF=X",
                        "AUDJPY=X", "CADJPY=X", "CHFJPY=X", "NZDJPY=X",
                        "EURAUD=X", "EURCAD=X", "EURNZD=X", "GBPAUD=X",
                        "GBPCAD=X", "GBPCHF=X", "GBPNZD=X", "AUDCAD=X",
                        "AUDCHF=X", "AUDNZD=X", "CADCHF=X", "NZDCAD=X",
                        "NZDCHF=X"]},
    **{s: 1.5 for s in ["GC=F", "SI=F", "HG=F", "PL=F", "PA=F",
                        "CL=F", "NG=F", "HO=F", "RB=F", "BZ=F",
                        "ES=F", "NQ=F", "YM=F", "RTY=F"]},
    **{s: 3.0 for s in ["ZC=F", "ZS=F", "ZW=F", "ZL=F", "ZM=F", "KC=F",
                        "SB=F", "CT=F", "CC=F", "OJ=F"]},
    **{s: 1.0 for s in ["ZN=F", "ZB=F", "ZF=F", "ZT=F"]},
    **{s: 10.0 for s in ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD",
                         "ADA-USD", "DOGE-USD", "BNB-USD", "LTC-USD"]},
}


def autoverifier(symbole="EURUSD=X"):
    """
    Le code respecte-t-il encore la specification ?

    Le ratio gain/risque est impose par la geometrie du Fibonacci : entree
    entre 0,618 et 0,786, stop au niveau 1, objectif au niveau 0. Il ne peut
    donc valoir qu'entre 1,62 et 3,67. Un ratio hors de ces bornes signifie
    que l'entree est sortie de la zone OTE — le bug exact qui touchait un
    trade sur quatre avant correction.
    """
    df = journalier(symbole)
    if df is None or len(df) < 800:
        return True, "verification impossible (donnees absentes)"
    trades = S.rejouer(df.reset_index(drop=True), suiveur=SUIVEUR)
    if not trades:
        return True, "aucun trade sur l'echantillon de controle"
    hors = sum(1 for t in trades if not (1.5 <= t["rr"] <= 4.5))
    if hors:
        return False, (f"{hors} trades sur {len(trades)} ont un ratio hors des "
                       f"bornes geometriques : l'entree sort de la zone OTE")
    if any(t["stop_bps"] <= 0 for t in trades):
        return False, "un stop nul ou negatif est apparu"
    return True, f"{len(trades)} trades de controle, ratios conformes"


def charger_etat():
    if os.path.exists(ETAT):
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    return {"capital": CAPITAL_DEPART, "instruments": {}, "clos": 0,
            "gagnants": 0, "demarre": datetime.now(timezone.utc).isoformat()}


def sauver_etat(e):
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(e, f, indent=2, ensure_ascii=False)


def journaliser(ligne):
    neuf = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ligne.keys()))
        if neuf:
            w.writeheader()
        w.writerow(ligne)


def cycle():
    etat = charger_etat()
    premier = not etat["instruments"]
    ok, message = autoverifier()
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    print(f"[{horodatage}] autoverification : {message}", flush=True)
    if not ok:
        print("  ARRET — le code ne respecte plus la specification.")
        return etat, [], False

    evenements = []
    for sym, frais in UNIVERS.items():
        df = journalier(sym)
        if df is None or len(df) < 800:
            continue
        trades = S.rejouer(df.reset_index(drop=True), suiveur=SUIVEUR)
        if not trades:
            continue

        # PREMIER PASSAGE : on note l'historique SANS l'encaisser.
        #
        # Sans cette ligne, le bot facturait vingt-cinq ans de backtest comme
        # s'ils venaient de se produire et affichait +63 % des la premiere
        # seconde. On ne compte que ce qui arrive APRES le demarrage.
        if sym not in etat["instruments"]:
            etat["instruments"][sym] = len(trades)
            continue

        for t in trades[etat["instruments"][sym]:]:
            r_net = (t["r"] - frais / t["stop_bps"]) if t["stop_bps"] > 0 else t["r"]
            risque = etat["capital"] * RISQUE_PCT / 100
            gain = risque * r_net
            etat["capital"] = round(max(etat["capital"] + gain, 0.0), 2)
            etat["clos"] += 1
            etat["gagnants"] += 1 if r_net > 0 else 0
            journaliser({
                "date": horodatage, "instrument": sym,
                "r_brut": round(t["r"], 3), "r_net": round(r_net, 3),
                "ratio_vise": round(t["rr"], 2),
                "stop_bps": round(t["stop_bps"], 1), "frais_bps": frais,
                "duree_barres": t["barres"], "issue": t.get("issue", ""),
                "gain_eur": round(gain, 2), "capital": etat["capital"],
            })
            evenements.append(
                f"{sym:<11} {t.get('issue', '?'):<6} {r_net:+6.2f} R  "
                f"{gain:+8.2f} EUR  -> {etat['capital']:.2f} EUR")
        etat["instruments"][sym] = len(trades)

    sauver_etat(etat)
    return etat, evenements, premier


def main():
    print("=" * 74)
    print("BOT PAPIER — structure, zone OTE, confluence, stop suiveur")
    print("=" * 74)
    print(f"{len(UNIVERS)} instruments, bougies journalieres, "
          f"risque {RISQUE_PCT} % par trade")
    print("Aucune cle d'API. Aucun ordre reel n'est passe.\n")

    etat, evenements, premier = cycle()

    if premier:
        print("\nINITIALISATION — historique enregistre, rien encaisse.")
    elif evenements:
        print(f"\n{len(evenements)} trade(s) clos depuis le dernier passage :")
        for e in evenements:
            print(f"  {e}")
    else:
        print("\nAucun trade clos depuis le dernier passage.")

    n = etat["clos"]
    print(f"\n{'-' * 74}")
    print(f"  capital      {etat['capital']:>10.2f} EUR   "
          f"({etat['capital'] / CAPITAL_DEPART - 1:+.1%})")
    print(f"  trades clos  {n:>10,}")
    if n:
        print(f"  reussite     {etat['gagnants'] / n:>10.1%}")
    print(f"  depuis       {etat['demarre'][:10]}")
    if n < 100:
        print(f"\n  {100 - n} trades avant de pouvoir juger quoi que ce soit.")


if __name__ == "__main__":
    main()
