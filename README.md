# Bot papier — structure, zone OTE, confluence

Trading **en papier uniquement**. Aucune clé d'API, aucun ordre réel.

---

## La stratégie, dans l'ordre

```
1. TENDANCE      structure de marché : sommets et creux ascendants = haussier.
                 En range, on ne fait rien — 40 à 60 % du temps.

2. JAMBE         le dernier creux confirmé qui précède le dernier sommet
                 confirmé. Fibonacci tracé dessus : 0 au bout de l'impulsion,
                 1 à son origine.

3. ZONE OTE      entre 0,618 et 0,786. Elle AUTORISE l'entrée, elle ne la
                 déclenche pas.

4. CONFLUENCE    un objet réel dans la zone : écart de juste valeur,
                 déséquilibre de volume, bloc d'ordres, ou cassure-retest.

5. ENTRÉE        sur la confluence. La tendance est REVÉRIFIÉE à cet instant.

6. STOP          niveau 1 du Fibonacci.  OBJECTIF  niveau 0.
                 Stop suiveur sur les creux de structure.
```

Le ratio gain/risque n'est **pas un réglage** : il découle de la géométrie.
Entrée à 0,618 → 1,62. Entrée à 0,786 → 3,67. Un paramètre de moins, donc une
façon de moins de se tromper.

---

## Ce qui a été mesuré

73 instruments, 8 familles d'actifs, deux échelles de temps, réserve
verrouillée sur les 30 % les plus récents.

| échelle | période | R net par trade | t | trades |
|---|---|---|---|---|
| horaire | étude | +0,035 | +1,92 | 4 986 |
| horaire | réserve | +0,050 | +1,82 | 2 260 |
| journalier | étude | +0,027 | +1,10 | 2 628 |
| journalier | réserve | +0,039 | +1,06 | 1 189 |

**Quatre mesures sur quatre positives.** Combinées : t ≈ 2,5 à 3,0.

Au-dessus du seuil conventionnel de 2. **En dessous du seuil de ~3,4** qu'exige
le nombre d'essais accumulés pendant la recherche.

### Ce que la mesure ne dit pas

Aucune famille d'actifs ne garde le même signe d'une échelle à l'autre —
4 sur 8, soit exactement le hasard. Les métaux dominent en horaire (+0,373 sur
la réserve) et disparaissent en journalier (−0,001).

**Conséquence : on applique la stratégie à tout, on ne sélectionne rien.**
Choisir « les meilleures familles » reviendrait à choisir sur du bruit.

---

## Pourquoi du papier

L'avantage est réel mais faible, et sous le seuil de preuve. Il faut environ
**100 trades avant de pouvoir en dire quoi que ce soit** — soit neuf mois au
rythme de 2,2 trades par instrument et par an.

Le bot ne peut pas passer d'ordre. C'est délibéré.

---

## Protection contre les erreurs

**Le bot n'a pas de code à lui.** Il rejoue `strategie/strategie_ote.py` — le
fichier même du backtest — et encaisse ce qui s'est fermé depuis la veille.
Une divergence entre backtest et exécution est structurellement impossible.

**Il s'autovérifie avant chaque cycle.** Le ratio ne pouvant valoir qu'entre
1,62 et 3,67 par construction, tout écart signale que l'entrée est sortie de
la zone. Dans ce cas **le bot s'arrête** plutôt que de continuer à dériver.

Six bugs ont été trouvés pendant la recherche, dont deux fabriquaient un faux
avantage :

| bug | effet |
|---|---|
| tendance vérifiée au dessin, pas à l'entrée | 75 trades sur 159 à contresens |
| bord de confluence hors de la zone | 26 % des entrées hors OTE |
| filtre d'entrée lisant le bas complet de la bougie | +0,19 R fabriqués |
| échantillons chevauchants | t multiplié par 12 |
| cache partiel rechargé en silence | 1 mois de données au lieu de 25 ans |
| historique encaissé au démarrage | +63 % affichés à la première seconde |

---

## Utilisation

```bash
pip install -r requirements.txt
python bot.py
```

Le premier passage enregistre l'historique **sans l'encaisser** et part de
1 000 € à zéro trade. Ensuite, un cycle par jour ouvré via GitHub Actions.

`etat.json` contient le capital et le compteur par instrument.
`trades.csv` contient chaque trade clos, avec son R brut, son R net, sa durée
et les frais appliqués.

---

## Frais

Comptés par instrument, en points de base d'aller-retour : 1,0 pour les
devises majeures, 2,2 pour les croisées, 1,5 pour métaux, énergie et indices,
3,0 pour l'agricole, 10 pour la crypto.

```
part des frais dans le risque    1,0 %
```

Contre 48 % pour le scalping 5 minutes testé au début du projet. C'est le seul
régime où l'arithmétique cesse de peser — un stop médian de 259 bps rend les
frais négligeables.
