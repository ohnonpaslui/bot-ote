"""
confluences.py — Ce qui declenche l'entree A L'INTERIEUR de la zone OTE.

LE POINT CENTRAL DE LA SPECIFICATION

« L'OTE est une zone et non un signal d'entree : le prix peut tres bien
passer dedans mais rien ne se passe. »

C'est exactement l'erreur des tests precedents — ils entraient des que le
prix touchait 0,618. Ici la zone ne fait qu'AUTORISER l'entree ; ce qui la
DECLENCHE est un objet precis situe dedans.

LES QUATRE OBJETS

  ecart de juste valeur (FVG)   trois bougies : la premiere et la troisieme
                                ne se touchent pas. Le vide entre les deux
                                n'a jamais ete negocie.

  desequilibre de volume (VI)   deux bougies dont les CORPS ne se touchent
                                pas, meme si les meches se chevauchent. Plus
                                fin qu'un FVG, et plus frequent.

  bloc d'ordres (OB)            la derniere bougie de sens contraire avant
                                l'impulsion. L'idee : c'est la que le gros
                                intervenant s'est positionne avant de pousser.

  cassure + retest              un niveau franchi, puis revisite par-dessous
                                (ou par-dessus). Le plus simple des quatre,
                                et le seul qui ne demande aucune convention.

CE QUI EST IMPOSE A TOUS

Chacun doit s'etre FORME AVANT la bougie courante et se situer DANS la zone
OTE. Un objet detecte a l'indice i n'est utilisable qu'a partir de i+1 : une
bougie ne peut pas declencher une entree pendant qu'elle se forme.
"""

import numpy as np
import pandas as pd

AGE_MAX = 80        # bougies : au-dela, l'objet est ecarte


def fvg(df, i, sens, min_taille=0.0):
    """
    Ecarts de juste valeur formes jusqu'a i-1, dans le sens voulu.

    Haussier : le bas de la bougie k depasse le haut de la bougie k-2.
    Le vide va de high[k-2] a low[k] — c'est la zone qu'on veut revoir.
    """
    h, l = df["high"].values, df["low"].values
    out = []
    # On ne remonte pas plus loin que l'age au-dela duquel un objet est
    # ecarte de toute facon : scanner tout l'historique donnait le meme
    # resultat pour un cout croissant avec la longueur de la serie.
    for k in range(max(2, i - AGE_MAX), i + 1):
        if sens > 0 and l[k] > h[k - 2]:
            taille = l[k] - h[k - 2]
            if taille >= min_taille:
                out.append((h[k - 2], l[k], k))
        elif sens < 0 and h[k] < l[k - 2]:
            taille = l[k - 2] - h[k]
            if taille >= min_taille:
                out.append((h[k], l[k - 2], k))
    return out


def volume_imbalance(df, i, sens, min_taille=0.0):
    """
    Desequilibres de volume : deux corps qui ne se touchent pas.

    Contrairement au FVG, on ignore les meches. Le vide se mesure entre la
    cloture d'une bougie et l'ouverture de la suivante.
    """
    o, c = df["open"].values, df["close"].values
    out = []
    for k in range(max(1, i - AGE_MAX), i + 1):
        bas_k1, haut_k1 = min(o[k - 1], c[k - 1]), max(o[k - 1], c[k - 1])
        bas_k, haut_k = min(o[k], c[k]), max(o[k], c[k])
        if sens > 0 and bas_k > haut_k1:
            if bas_k - haut_k1 >= min_taille:
                out.append((haut_k1, bas_k, k))
        elif sens < 0 and haut_k < bas_k1:
            if bas_k1 - haut_k >= min_taille:
                out.append((haut_k, bas_k1, k))
    return out


def order_blocks(df, i, sens, impulsion=3, force=1.5):
    """
    Blocs d'ordres : la derniere bougie de sens contraire avant une impulsion.

    Pour un bloc HAUSSIER on cherche la derniere bougie BAISSIERE suivie de
    `impulsion` bougies qui montent franchement. « Franchement » se mesure
    par rapport a l'amplitude moyenne recente : sans ce critere, la moindre
    bougie verte apres une rouge ferait un bloc, et on en trouverait partout.

    La zone retenue est le CORPS de la bougie, pas son amplitude totale.
    """
    o, c, h, l = (df[x].values for x in ("open", "close", "high", "low"))
    amp = pd.Series(h - l).rolling(20).mean().values
    out = []
    for k in range(max(20, i - AGE_MAX), i - impulsion + 1):
        if not np.isfinite(amp[k]) or amp[k] <= 0:
            continue
        if sens > 0:
            if c[k] >= o[k]:                       # on veut une bougie baissiere
                continue
            deplacement = c[k + impulsion] - c[k]
        else:
            if c[k] <= o[k]:
                continue
            deplacement = c[k] - c[k + impulsion]
        if deplacement < force * amp[k]:
            continue
        out.append((min(o[k], c[k]), max(o[k], c[k]), k + impulsion))
    return out


def cassure_retest(df, i, sens, lookback=50, largeur=0.25):
    """
    Niveaux SIGNIFICATIFS casses puis revisites.

    Premiere version : je renvoyais tous les sommets des 50 dernieres bougies
    ayant ete franchis. Il y en avait toujours un quelque part, si bien que le
    filtre de confluence ne filtrait rien — les comptes de trades avec et sans
    confluence etaient identiques.

    Corrige : on n'accepte qu'un extremum LOCAL confirme (le plus haut de onze
    bougies centrees), franchi FRANCHEMENT — la cloture doit depasser le
    niveau d'au moins un quart de l'amplitude moyenne, pas l'effleurer.
    """
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    amp = pd.Series(h - l).rolling(20).mean().values
    debut = max(6, i - lookback)
    out = []
    for k in range(debut, i - 5):
        if not np.isfinite(amp[k]) or amp[k] <= 0:
            continue
        marge = largeur * amp[k]
        fen = slice(k - 5, k + 6)
        if sens > 0:
            if h[k] != h[fen].max():
                continue
            niveau = h[k]
            if any(c[j] > niveau + marge for j in range(k + 6, i + 1)):
                out.append((niveau - marge / 2, niveau + marge / 2, k))
        else:
            if l[k] != l[fen].min():
                continue
            niveau = l[k]
            if any(c[j] < niveau - marge for j in range(k + 6, i + 1)):
                out.append((niveau - marge / 2, niveau + marge / 2, k))
    return out


DETECTEURS = {
    "fvg": fvg,
    "volume_imbalance": volume_imbalance,
    "order_block": order_blocks,
    "cassure_retest": cassure_retest,
}



def recents(objets, i, age_max=AGE_MAX):
    """
    Ne garde que les objets formes recemment.

    Un ecart de juste valeur vieux de trois cents bougies n'est plus une zone
    que quiconque surveille. Sans cette borne, le nombre d'objets ne fait que
    croitre et finit par couvrir tout le graphique.
    """
    return [(a, b, k) for a, b, k in objets if i - k <= age_max]


def dans_zone(objets, zone_bas, zone_haut):
    """
    Ne garde que les objets qui CHEVAUCHENT la zone OTE.

    Un chevauchement suffit : un bloc d'ordres qui deborde legerement de la
    zone reste un bloc d'ordres. Exiger l'inclusion complete eliminerait la
    plupart des objets pour une raison purement geometrique.
    """
    return [(a, b, k) for a, b, k in objets
            if b >= zone_bas and a <= zone_haut]


def niveau_entree(objets, sens):
    """
    Le prix auquel on entre : le bord de l'objet que le prix atteint EN
    PREMIER en revenant dans la zone.

    Pour un achat, le prix descend : il rencontre d'abord le bord HAUT de
    l'objet le plus haut. Prendre le bord oppose supposerait que le prix
    traverse tout l'objet, ce qui n'arrive pas toujours.
    """
    if not objets:
        return None
    if sens > 0:
        return max(b for _, b, _ in objets)
    return min(a for a, _, _ in objets)


def trouver(df, i, sens, zone_bas, zone_haut, types=None, min_taille=0.0):
    """
    Toutes les confluences presentes dans la zone, par type.

    Renvoie un dict {type: (niveau_entree, nombre_d_objets)}. Le nombre
    compte : trois objets superposes au meme endroit ne valent pas un seul,
    et la specification parle bien de « confluence ».
    """
    out = {}
    for nom, fn in DETECTEURS.items():
        if types and nom not in types:
            continue
        if nom in ("order_block", "cassure_retest"):
            objets = fn(df, i, sens)
        else:
            objets = fn(df, i, sens, min_taille)
        gardes = dans_zone(recents(objets, i), zone_bas, zone_haut)
        if gardes:
            out[nom] = (niveau_entree(gardes, sens), len(gardes))
    return out
