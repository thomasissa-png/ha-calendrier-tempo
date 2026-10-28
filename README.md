# Calendrier Tempo EDF pour Home Assistant

[![Ouvrir dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thomasissa-png&repository=ha-calendrier-tempo&category=integration)
[![Validation](https://github.com/thomasissa-png/ha-calendrier-tempo/actions/workflows/validate.yml/badge.svg)](https://github.com/thomasissa-png/ha-calendrier-tempo/actions/workflows/validate.yml)

Intégration Home Assistant qui ajoute la **couleur Tempo EDF** du jour et de demain, les prévisions jusqu'à 15 jours, un calendrier des jours blancs et rouges, le prochain jour rouge et blanc, les jours rouges et blancs restants dans la saison et le **prix du kWh actuel**, prêt pour le tableau de bord Énergie.

Les données viennent de l'[API publique et gratuite de calendrier-tempo.fr](https://www.calendrier-tempo.fr/api-tempo) : aucun compte, aucune clé, rien à configurer.

## Fiabilité : ce qui fait foi, ce qui est prévu

| Horizon | Attribut `fiabilite` | Ce que cela veut dire |
|---|---|---|
| Aujourd'hui, demain une fois annoncé | `officielle` | Couleur publiée par EDF. **Seule elle fait foi.** |
| J+2 à J+5 | `fiable` | Prévision. C'est la zone sur laquelle le site mesure sa performance, la plus fiable. |
| J+6 à J+15 | `indicative` | Prévision à longue échéance : une tendance, pas une certitude. |

Une prévision pour demain, tant qu'EDF n'a pas annoncé la couleur, est marquée `fiable`. Les taux de réussite, calculés sur les prévisions réellement émises, sont publiés sur la page [méthodologie](https://www.calendrier-tempo.fr/methodologie) : cette intégration n'en affiche aucun.

## Installation

### Avec HACS (recommandé)

L'intégration est dans le catalogue par défaut de HACS :

1. Dans Home Assistant, ouvrez **HACS** et recherchez **Calendrier Tempo EDF**, puis cliquez sur **Télécharger**.
2. Redémarrez Home Assistant.
3. Allez dans **Paramètres > Appareils et services > Ajouter une intégration**, cherchez **Calendrier Tempo EDF** et validez.

Le bouton « Ouvrir dans HACS » en haut de cette page ouvre directement la fiche de l'intégration.

#### Si l'intégration n'apparaît pas dans la recherche

Ajoutez ce dépôt comme dépôt personnalisé, en solution de secours :

1. Dans **HACS**, ouvrez le menu (trois points en haut à droite), puis **Dépôts personnalisés**.
2. Collez l'adresse `https://github.com/thomasissa-png/ha-calendrier-tempo`.
3. Choisissez le type **Intégration**, puis **Ajouter**.
4. Puis recherchez **Calendrier Tempo EDF** et suivez les étapes 1 à 3 ci-dessus.

### Installation manuelle

1. Téléchargez l'archive de la dernière version sur [calendrier-tempo.fr/domotique/telecharger](https://www.calendrier-tempo.fr/domotique/telecharger) (ou ce dépôt).
2. Décompressez-la, puis copiez le dossier `custom_components/calendrier_tempo` dans le dossier `custom_components` de votre configuration Home Assistant (créez-le s'il n'existe pas).
3. Redémarrez Home Assistant, puis ajoutez l'intégration depuis **Paramètres > Appareils et services**.

Version minimale : Home Assistant 2025.3.

## Entités

Toutes les entités sont regroupées sous un appareil « Calendrier Tempo EDF ».

| Entité | Valeur | Fiabilité | Activée par défaut |
|---|---|---|---|
| `calendar.calendrier_tempo` | « Calendrier Tempo EDF » : un événement par jour blanc ou rouge, aujourd'hui compris, jusqu'à J+15 | officielle, fiable ou indicative selon le jour | oui |
| `sensor.calendrier_tempo_couleur_aujourd_hui` | `bleu`, `blanc` ou `rouge` | officielle | oui |
| `sensor.calendrier_tempo_couleur_actuelle` | couleur qui s'applique maintenant : celle de la veille jusqu'à 6 h | officielle | oui |
| `sensor.calendrier_tempo_periode` | `hp` (heures pleines, 6 h à 22 h) ou `hc` (heures creuses) | heure de Paris | oui |
| `sensor.calendrier_tempo_prix_kwh_actuel` | « Prix du kWh actuel » en EUR/kWh TTC : heures pleines ou creuses de la couleur de la journée Tempo en cours | grille publiée par l'API | oui |
| `sensor.calendrier_tempo_couleur_demain` | `bleu`, `blanc` ou `rouge`, inconnu tant qu'EDF n'a pas annoncé | officielle | oui |
| `sensor.calendrier_tempo_prevision_j2` à `_j5` | couleur prévue dans 2, 3, 4 ou 5 jours | fiable | oui |
| `sensor.calendrier_tempo_prevision_j6` à `_j15` | couleur prévue dans 6 à 15 jours | indicative | **non** |
| `sensor.calendrier_tempo_previsions_15_jours` | « Jours rouges sur 15 jours » : nombre de jours rouges (officiels ou prévus) d'aujourd'hui à J+15 | une par jour, dans `previsions` | oui |
| `sensor.calendrier_tempo_prochain_jour_rouge` | date du prochain jour rouge, officiel ou prévu, inconnu si aucun sur l'horizon | selon le jour | oui |
| `sensor.calendrier_tempo_prochain_jour_blanc` | date du prochain jour blanc, officiel ou prévu | selon le jour | oui |
| `sensor.calendrier_tempo_jours_rouges_restants` | jours rouges restants dans la saison | compteurs EDF, sinon calcul à partir des couleurs officielles (attribut `source`) | oui |
| `sensor.calendrier_tempo_jours_blancs_restants` | jours blancs restants dans la saison | idem | oui |

La journée Tempo va de 6 h à 6 h (heures pleines de 6 h à 22 h) : pour piloter un chauffage, utilisez `couleur_actuelle`, qui garde la couleur de la veille jusqu'à 6 h.

Les capteurs J+6 à J+15 sont créés mais désactivés : tout l'horizon est déjà dans le calendrier et dans le capteur 15 jours. Pour en activer un : ouvrez l'appareil « Calendrier Tempo EDF » (**Paramètres > Appareils et services**), affichez les entités désactivées, ouvrez celle voulue et activez-la dans ses paramètres.

### Le calendrier

- `Jour rouge (officiel)`, `Jour blanc (officiel)` : couleur publiée par EDF.
- `Jour rouge prévu (probabilité 62 %)`, `Jour blanc prévu (probabilité 40 %)` : prévision. La description précise l'échéance (J+N), la fiabilité, les trois probabilités et la température moyenne prévue.
- `Jour blanc ou rouge ? (50 %)` : prévision hésitante, quand un jour rouge est possible et que la deuxième couleur la plus probable est à moins de 30 points de la couleur prévue (et au-dessus de 15 %), comme sur calendrier-tempo.fr. Entre blanc et bleu, la couleur la plus probable est donnée seule, avec son pourcentage. La description donne les deux probabilités.
- Les jours bleus, couleur par défaut d'environ 300 jours par an, ne créent pas d'événement. Le calendrier est donc « activé » (`on`) uniquement un jour blanc ou rouge, et les déclencheurs de calendrier ne réagissent qu'aux jours qui coûtent cher. Un calendrier vide signifie qu'aucun jour blanc ou rouge n'est prévu sur l'horizon (ou que les données sont indisponibles).

Les textes des événements suivent la langue de Home Assistant (français, sinon anglais).

### Attributs

- Prévisions J+2 à J+15 : `date`, `fiabilite`, `officielle`, `probabilite_bleu`, `probabilite_blanc`, `probabilite_rouge` (entre 0 et 1), `score_risque`, `temp_min_prevue`, `temp_max_prevue`, `temp_moy_prevue`, `raison`, `hesitation` (vrai ou faux), `seconde_couleur` (vide sans hésitation) et `libelle` (texte du site, par exemple « Blanc ou rouge ? » ou « Blanc »).
- Couleur aujourd'hui et demain : `date`, `code` (1, 2, 3), `officielle`, `fiabilite`, `prix_hp`, `prix_hc` (EUR/kWh de cette couleur). Couleur actuelle : `date` (journée Tempo en cours), `officielle`, `fiabilite`, `prix_hp`, `prix_hc`.
- Prix du kWh actuel : `periode` (`hp` ou `hc`), `couleur`, `date` (journée Tempo en cours), `grille` (prix `hp` et `hc` des trois couleurs), `date_effet` (date d'entrée en vigueur de la grille).
- Prochain jour rouge ou blanc : `rouge_prevu` ou `blanc_prevu` (vrai ou faux), `jours_avant`, `officielle`, `fiabilite` et les probabilités.
- Prévisions 15 jours : `horizon_jours` (15 en temps normal), `jours_blancs`, `jours_rouges_officiels`, `generee_le`, et `previsions`, la liste complète, un élément par jour : `date`, `jour` (0 = aujourd'hui), `couleur`, `officielle`, `fiabilite`, `probabilite_bleu`, `probabilite_blanc`, `probabilite_rouge`. Cette liste n'est pas enregistrée dans l'historique, pour ne pas alourdir la base.
- Jours restants : `total_saison`, `debut_saison`, `fin_saison`, `source` (`edf` ou `calcul`).

Les couleurs sont stockées en minuscules (`bleu`, `blanc`, `rouge`) et affichées « Bleu », « Blanc », « Rouge ». Dans vos automatisations, comparez toujours avec la valeur en minuscules. Un jour officiel a une probabilité de 1 pour sa couleur, 0 pour les autres.

Rafraîchissement (heure de Paris) : toutes les 30 minutes (4 petites requêtes), à 0 h 05 pour le changement de jour, et à 11 h 35 pour récupérer la couleur de demain annoncée par EDF. Si les prévisions ou les jours restants ne répondent pas, les dernières valeurs reçues sont conservées 24 h au plus et les couleurs officielles restent à jour. Si les couleurs officielles ne répondent pas, les entités passent « indisponibles ». Après un échec, une seule nouvelle tentative a lieu 5 minutes plus tard, puis le cycle de 30 minutes reprend, sans relance en rafale.

## Prix du kWh et tableau de bord Énergie

Le capteur `sensor.calendrier_tempo_prix_kwh_actuel` donne le prix du kWh qui s'applique maintenant, en EUR/kWh TTC (prix du kWh seul, hors abonnement) :

- de 6 h à 22 h, le prix heures pleines de la couleur du jour ;
- de 22 h à 6 h, le prix heures creuses ; entre minuit et 6 h, c'est la couleur de la veille qui s'applique, car la journée Tempo court de 6 h à 6 h.

Le prix est recalculé dans Home Assistant à 6 h, 22 h et minuit, sans requête supplémentaire. Les prix viennent de la grille publiée par l'API de calendrier-tempo.fr : l'intégration n'en contient aucun. Tant que l'API ne publie pas cette grille, ou si la couleur de la journée Tempo n'est pas connue, le capteur reste « inconnu ». Pendant une panne de l'API, il continue d'être calculé avec les dernières données reçues (grille gardée 24 h au plus).

Pour l'utiliser dans le tableau de bord Énergie :

1. Ouvrez **Paramètres > Tableaux de bord > Énergie**.
2. Dans **Réseau électrique**, modifiez votre consommation (ou ajoutez-la).
3. Choisissez **Utiliser une entité avec le prix actuel**, puis `sensor.calendrier_tempo_prix_kwh_actuel`.

Home Assistant calcule alors le coût de votre consommation au prix de la couleur et de la période en cours. Le capteur a pour unité `EUR/kWh` et une classe d'état `measurement` : son historique est conservé dans les statistiques.

## Exemples

### Veille d'un jour rouge (couleur officielle EDF)

```yaml
alias: "Tempo : jour rouge demain"
triggers:
  - trigger: state
    entity_id: sensor.calendrier_tempo_couleur_demain
    to: "rouge"
    not_from: "unavailable"
actions:
  - action: notify.notify
    data:
      title: "Jour Tempo rouge demain"
      message: "EDF annonce un jour rouge demain : pensez à décaler vos usages."
mode: single
```

Le déclencheur ne réagit qu'à la couleur annoncée par EDF, jamais à une prévision ; `not_from` évite une seconde notification au retour d'une panne.

### Jour rouge prévu dans les 5 jours, avec une probabilité d'au moins 50 %

```yaml
alias: "Tempo : rouge probable dans les 5 jours"
triggers:
  - trigger: template
    value_template: >-
      {{ state_attr('sensor.calendrier_tempo_previsions_15_jours', 'previsions') | default([], true)
         | selectattr('jour', '>=', 1) | selectattr('jour', '<=', 5)
         | rejectattr('probabilite_rouge', 'none')
         | selectattr('probabilite_rouge', '>=', 0.5) | list | count > 0 }}
actions:
  - action: notify.notify
    data:
      title: "Jour rouge probable"
      message: >-
        {% set rouges = state_attr('sensor.calendrier_tempo_previsions_15_jours', 'previsions') | default([], true)
           | selectattr('jour', '>=', 1) | selectattr('jour', '<=', 5)
           | rejectattr('probabilite_rouge', 'none')
           | selectattr('probabilite_rouge', '>=', 0.5) | list %}
        Rouge probable :
        {%- for j in rouges %} {{ j.date }} ({{ (j.probabilite_rouge * 100) | round }} %{{ ', officiel' if j.officielle else '' }}){{ ',' if not loop.last }}{% endfor %}.
        Seule la couleur publiée par EDF fait foi.
mode: single
```

Changez `5` pour regarder plus loin (jusqu'à `15`), en gardant à l'esprit qu'au-delà de J+5 la prévision est une tendance.

### Carte calendrier

Dans un tableau de bord, **Modifier > Ajouter une carte > Manuel** :

```yaml
type: calendar
entities:
  - calendar.calendrier_tempo
initial_view: dayGridMonth
```

Vous pouvez aussi réagir au début d'un événement du calendrier (déclencheur **Calendrier**, événement « Début ») : il ne se produit que les jours blancs et rouges.

## Liens

- Configuration domotique sans intégration (capteurs REST, Jeedom, Domoticz) : [calendrier-tempo.fr/domotique](https://www.calendrier-tempo.fr/domotique)
- Documentation de l'API : [calendrier-tempo.fr/api-tempo](https://www.calendrier-tempo.fr/api-tempo)
- Méthode de prévision et taux de réussite publiés : [calendrier-tempo.fr/methodologie](https://www.calendrier-tempo.fr/methodologie)
- Calendrier et prévisions : [calendrier-tempo.fr](https://www.calendrier-tempo.fr/)
- Signaler un problème : [tickets GitHub](https://github.com/thomasissa-png/ha-calendrier-tempo/issues), ou jean-pierre@calendrier-tempo.fr

Service gratuit et indépendant, sans garantie de disponibilité, non affilié à EDF ni à RTE.

## English

Home Assistant custom integration for the French **EDF Tempo** electricity tariff, with **forecasts up to 15 days ahead**. It adds today's and tomorrow's official Tempo color, a **calendar of white and red days** (`calendar.calendrier_tempo`, official and forecast days clearly labelled, blue days left out so the calendar is `on` only on costly days), D+2 to D+5 forecast sensors, a **red days in the next 15 days** sensor (state = number of red days up to D+15, attribute `previsions` = one item per day with color, probabilities, `officielle` and `fiabilite`), the next red and white day, and the remaining red and white days of the season. Sensors for D+6 to D+15 exist but are disabled by default.

Reliability (`fiabilite` attribute): `officielle` = color published by EDF, the only authoritative one; `fiable` = forecast up to D+5 (D+2 to D+5 is the range where the site measures its performance, the most reliable one); `indicative` = D+6 to D+15, a trend rather than a certainty. Success rates are published on the [methodology page](https://www.calendrier-tempo.fr/methodologie), not in this integration.

Data comes from the free public API of [calendrier-tempo.fr](https://www.calendrier-tempo.fr/api-tempo) (no account, no key). Requires Home Assistant 2025.3 or later. Install through HACS as a custom repository (`https://github.com/thomasissa-png/ha-calendrier-tempo`, type *Integration*), or manually from the [archive](https://www.calendrier-tempo.fr/domotique/telecharger), restart Home Assistant, then add **Calendrier Tempo EDF** from *Settings > Devices & services*. Sensor states are `bleu` (blue), `blanc` (white) and `rouge` (red); calendar event texts follow the Home Assistant language (French or English). The Tempo day runs from 6:00 to 6:00 (peak hours 6:00 to 22:00): `couleur_actuelle` keeps the previous day's color until 6:00 and `periode` is `hp` or `hc`. Updates every 30 minutes, at 0:05 and at 11:35 (Paris time) after EDF announces tomorrow's color, with a single retry 5 minutes after a failure. Not affiliated with EDF or RTE.

## Licence

[MIT](LICENSE)
