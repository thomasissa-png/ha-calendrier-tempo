# Calendrier Tempo EDF pour Home Assistant

[![Ouvrir dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thomasissa-png&repository=ha-calendrier-tempo&category=integration)
[![Validation](https://github.com/thomasissa-png/ha-calendrier-tempo/actions/workflows/validate.yml/badge.svg)](https://github.com/thomasissa-png/ha-calendrier-tempo/actions/workflows/validate.yml)

Intégration Home Assistant qui ajoute la **couleur Tempo EDF du jour et de demain**, les **prévisions de J+2 à J+5**, le **prochain jour rouge prévu** et les **jours rouges et blancs restants** dans la saison.

Les données viennent de l'[API publique et gratuite de calendrier-tempo.fr](https://www.calendrier-tempo.fr/api-tempo) : aucun compte, aucune clé, rien à configurer.

## Installation

### Avec HACS (recommandé)

Tant que l'intégration n'est pas dans le catalogue par défaut de HACS, ajoutez ce dépôt comme dépôt personnalisé :

1. Dans Home Assistant, ouvrez **HACS**, puis le menu (trois points en haut à droite) et **Dépôts personnalisés**.
2. Collez l'adresse `https://github.com/thomasissa-png/ha-calendrier-tempo`, choisissez le type **Intégration**, puis **Ajouter**.
3. Recherchez **Calendrier Tempo EDF** dans HACS, cliquez sur **Télécharger**.
4. Redémarrez Home Assistant.
5. Allez dans **Paramètres > Appareils et services > Ajouter une intégration**, cherchez **Calendrier Tempo EDF** et validez.

Le bouton « Ouvrir dans HACS » en haut de cette page fait les étapes 1 à 3 pour vous.

Une fois l'intégration acceptée dans le catalogue par défaut de HACS, l'étape 2 ne sera plus nécessaire : il suffira de la rechercher dans HACS.

### Installation manuelle

1. Téléchargez la dernière version (ou ce dépôt).
2. Copiez le dossier `custom_components/calendrier_tempo` dans le dossier `custom_components` de votre configuration Home Assistant (créez-le s'il n'existe pas).
3. Redémarrez Home Assistant, puis ajoutez l'intégration depuis **Paramètres > Appareils et services**.

Version minimale : Home Assistant 2025.2.

## Capteurs

Tous les capteurs sont regroupés sous un appareil « Calendrier Tempo EDF ».

| Entité | Valeur | Attributs utiles |
|---|---|---|
| `sensor.calendrier_tempo_couleur_aujourd_hui` | `bleu`, `blanc` ou `rouge` (couleur officielle EDF) | `date`, `code` (1, 2, 3), `officielle` |
| `sensor.calendrier_tempo_couleur_demain` | `bleu`, `blanc` ou `rouge`, inconnu tant qu'EDF n'a pas publié | `date`, `code`, `officielle` |
| `sensor.calendrier_tempo_prevision_j2` | couleur prévue dans 2 jours | `date`, `probabilite_bleu`, `probabilite_blanc`, `probabilite_rouge` (entre 0 et 1), `score_risque`, `temp_min_prevue`, `temp_max_prevue`, `temp_moy_prevue`, `raison`, `confirmed` |
| `sensor.calendrier_tempo_prevision_j3` | couleur prévue dans 3 jours | idem |
| `sensor.calendrier_tempo_prevision_j4` | couleur prévue dans 4 jours | idem |
| `sensor.calendrier_tempo_prevision_j5` | couleur prévue dans 5 jours | idem |
| `sensor.calendrier_tempo_prochain_jour_rouge` | date du prochain jour rouge (officiel ou prévu dans les prochains jours), inconnu si aucun | `rouge_prevu` (vrai ou faux), `jours_avant`, `probabilite_rouge`, `confirmed` |
| `sensor.calendrier_tempo_jours_rouges_restants` | nombre de jours rouges restants dans la saison | `total_saison`, `debut_saison`, `fin_saison` |
| `sensor.calendrier_tempo_jours_blancs_restants` | nombre de jours blancs restants dans la saison | `total_saison`, `debut_saison`, `fin_saison` |

Les couleurs sont stockées en minuscules (`bleu`, `blanc`, `rouge`) et affichées « Bleu », « Blanc », « Rouge » dans l'interface. Dans vos automatisations, comparez toujours avec la valeur en minuscules. Les attributs ne sont présents que si l'API les fournit.

Rafraîchissement : toutes les 30 minutes (4 petites requêtes), plus une mise à jour juste après minuit pour le changement de jour. En cas de panne réseau ou de l'API, les capteurs passent « indisponibles » et l'intégration réessaie au cycle suivant, sans relance en rafale.

## Exemples d'automatisations

### Veille d'un jour rouge (couleur officielle EDF)

```yaml
alias: "Tempo : jour rouge demain"
triggers:
  - trigger: state
    entity_id: sensor.calendrier_tempo_couleur_demain
    to: "rouge"
actions:
  - action: notify.notify
    data:
      title: "Jour Tempo rouge demain"
      message: "EDF annonce un jour rouge demain : pensez à décaler vos usages."
mode: single
```

### Anticiper un jour rouge prévu dans 2 jours (prévision indicative)

```yaml
alias: "Tempo : rouge prévu dans 2 jours"
triggers:
  - trigger: state
    entity_id: sensor.calendrier_tempo_prevision_j2
    to: "rouge"
actions:
  - action: notify.notify
    data:
      title: "Jour rouge possible"
      message: >-
        Jour rouge prévu le {{ state_attr('sensor.calendrier_tempo_prevision_j2', 'date') }}
        (prévision indicative, la couleur officielle EDF est publiée la veille).
mode: single
```

## Fiabilité

- **Seule la couleur publiée par EDF fait foi.** Les capteurs « aujourd'hui » et « demain » reprennent la couleur officielle dès sa publication.
- **Les prévisions sont indicatives.** Elles servent à anticiper, pas à décider à coup sûr.
- La performance du site est mesurée sur les prévisions faites **2 à 5 jours à l'avance**. Les taux publiés, calculés sur les prévisions réellement émises, sont sur la page [méthodologie](https://www.calendrier-tempo.fr/methodologie). Cette intégration n'affiche aucun taux de réussite.
- Service gratuit et indépendant, sans garantie de disponibilité, non affilié à EDF ni à RTE.

## Liens

- Configuration domotique sans intégration (capteurs REST, Jeedom, Domoticz) : [calendrier-tempo.fr/domotique](https://www.calendrier-tempo.fr/domotique)
- Documentation de l'API : [calendrier-tempo.fr/api-tempo](https://www.calendrier-tempo.fr/api-tempo)
- Calendrier et prévisions : [calendrier-tempo.fr](https://www.calendrier-tempo.fr/)
- Signaler un problème : [tickets GitHub](https://github.com/thomasissa-png/ha-calendrier-tempo/issues), ou jean-pierre@calendrier-tempo.fr

## English

Home Assistant custom integration for the French **EDF Tempo** electricity tariff. It adds today's and tomorrow's official Tempo color, D+2 to D+5 forecasts with probabilities, the next forecast red day and the remaining red and white days of the season, using the free public API of [calendrier-tempo.fr](https://www.calendrier-tempo.fr/api-tempo) (no account, no key).

Install through HACS as a custom repository (`https://github.com/thomasissa-png/ha-calendrier-tempo`, type *Integration*), restart Home Assistant, then add **Calendrier Tempo EDF** from *Settings > Devices & services*. Sensor states are `bleu` (blue), `blanc` (white) and `rouge` (red). Only the color published by EDF is authoritative; forecasts are indicative. Not affiliated with EDF or RTE.

## Licence

[MIT](LICENSE)
