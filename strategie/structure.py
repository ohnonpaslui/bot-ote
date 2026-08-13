"""
structure.py — La tendance, avant tout le reste.

POURQUOI CETTE BRIQUE VIENT EN PREMIER

« Avant meme de commencer a vouloir trader, le bot doit analyser la
tendance. » C'est la premiere regle de la specification, et elle commande
tout : sans tendance identifiee, il n'y a ni jambe a mesurer, ni zone OTE a
tracer, ni sens dans lequel entrer.

CE QUE « TENDANCE » VEUT DIRE ICI

Pas une moyenne mobile — une STRUCTURE. Le marche est haussier quand il fait
des sommets plus hauts ET des creux plus hauts. Baissier quand il fait des
sommets plus bas ET des creux plus bas. Tout le reste est un range, et dans
un range on ne trade pas.

C'est la lecture des concepts de structure de marche, et elle a un avantage
sur une moyenne mobile : elle donne aussi les POINTS qui servent a tracer le
Fibonacci. Une moyenne dit « ca monte » ; une structure dit « ca monte, et
voici le creux qui a lance le mouvement ».

LE PIEGE DU RETARD, ET COMMENT ON LE TRAITE

Un sommet fractal n'est confirme que N bougies apres son apparition : on ne
sait qu'un point etait un sommet qu'en voyant qu'il n'a pas ete depasse. Tout
le code ci-dessous n'utilise donc un pivot qu'a partir de l'indice ou il est
CONFIRME, jamais a l'indice ou il s'est forme. Sans cette precaution, la
structure « connait » l'avenir — et c'est l'erreur qui avait fabrique un faux
avantage de +0,19 R au test precedent.
"""

import numpy as np
import pandas as pd

PIVOT_N = 5          # bougies de chaque cote pour confirmer un extremum


def pivots(df, n=PIVOT_N):
    """
    Sommets et creux fractals, avec leur indice de CONFIRMATION.

    Renvoie deux listes de (indice_du_pivot, indice_de_confirmation, prix).
    L'indice de confirmation vaut indice_du_pivot + n : c'est la premiere
    bougie a partir de laquelle un observateur pouvait savoir que ce point
    etait un extremum.
    """
    h, l = df["high"].values, df["low"].values
    hauts, bas = [], []
    for i in range(n, len(df) - n):
        fen = slice(i - n, i + n + 1)
        if h[i] == h[fen].max():
            hauts.append((i, i + n, h[i]))
        if l[i] == l[fen].min():
            bas.append((i, i + n, l[i]))
    return hauts, bas


def tendance(df, n=PIVOT_N):
    """
    Etat de la structure a chaque bougie : +1 haussier, -1 baissier, 0 range.

    Haussier   les deux derniers sommets confirmes montent ET les deux
               derniers creux confirmes montent
    Baissier   l'inverse
    Range      tout le reste — et on ne trade pas dans un range

    Renvoie aussi, pour chaque bougie, les deux points qui serviront a tracer
    le Fibonacci : le dernier creux et le dernier sommet, dans l'ordre ou ils
    se sont formes.
    """
    hauts, bas = pivots(df, n)
    etat = np.zeros(len(df), dtype=int)
    ancre_bas = np.full(len(df), np.nan)
    ancre_haut = np.full(len(df), np.nan)
    idx_bas = np.full(len(df), -1, dtype=int)
    idx_haut = np.full(len(df), -1, dtype=int)

    ih = ib = 0
    hh = bb = []
    for i in range(len(df)):
        # on n'integre un pivot qu'a partir de sa confirmation
        while ih < len(hauts) and hauts[ih][1] <= i:
            hh = hh + [hauts[ih]]
            ih += 1
        while ib < len(bas) and bas[ib][1] <= i:
            bb = bb + [bas[ib]]
            ib += 1
        if len(hh) < 2 or len(bb) < 2:
            continue

        sommets_montent = hh[-1][2] > hh[-2][2]
        creux_montent = bb[-1][2] > bb[-2][2]
        sommets_baissent = hh[-1][2] < hh[-2][2]
        creux_baissent = bb[-1][2] < bb[-2][2]

        if sommets_montent and creux_montent:
            etat[i] = +1
        elif sommets_baissent and creux_baissent:
            etat[i] = -1
        else:
            etat[i] = 0

        ancre_bas[i], idx_bas[i] = bb[-1][2], bb[-1][0]
        ancre_haut[i], idx_haut[i] = hh[-1][2], hh[-1][0]

    return pd.DataFrame({
        "tendance": etat,
        "dernier_bas": ancre_bas, "i_bas": idx_bas,
        "dernier_haut": ancre_haut, "i_haut": idx_haut,
    }, index=df.index)


def jambe(struct, i):
    """
    La jambe a mesurer : « le dernier plus bas qui a cree le dernier plus haut ».

    En tendance haussiere, on veut le creux qui PRECEDE le sommet — c'est lui
    qui a lance l'impulsion. Si le dernier creux est posterieur au dernier
    sommet, la jambe n'est pas encore formee et on ne trace rien.

    Renvoie (origine, extremite, sens) ou None.
    Le 0 du Fibonacci se place a l'EXTREMITE, le 1 a l'ORIGINE, conformement
    aux captures : sur le SPX, 0 = 5 091 (le sommet atteint) et 1 = 4 402
    (le creux de depart).
    """
    t = struct["tendance"].iloc[i]
    ib, ih = struct["i_bas"].iloc[i], struct["i_haut"].iloc[i]
    if t == 0 or ib < 0 or ih < 0:
        return None
    bas, haut = struct["dernier_bas"].iloc[i], struct["dernier_haut"].iloc[i]
    if not (np.isfinite(bas) and np.isfinite(haut)) or haut <= bas:
        return None

    if t > 0:
        # haussier : le creux doit venir AVANT le sommet
        if ib >= ih:
            return None
        return bas, haut, +1
    # baissier : le sommet doit venir avant le creux
    if ih >= ib:
        return None
    return haut, bas, -1


def niveaux_fib(origine, extremite):
    """
    Les cinq niveaux, avec 0 a l'extremite de l'impulsion et 1 a son origine.

    La zone OTE est comprise entre 0,618 et 0,786 — c'est-a-dire dans la
    moitie profonde du retracement, pas au milieu.
    """
    amplitude = extremite - origine
    return {n: extremite - n * amplitude
            for n in (0.0, 0.5, 0.618, 0.786, 1.0)}


def zone_ote(origine, extremite):
    """Bornes de la zone OTE, toujours rendues (basse, haute)."""
    f = niveaux_fib(origine, extremite)
    a, b = f[0.618], f[0.786]
    return (min(a, b), max(a, b))
