# Soumission au catalogue par défaut de HACS

Préparé le 17/10/2026 à partir des pages officielles relues ce jour-là :
[include](https://hacs.xyz/docs/publish/include), [integration](https://hacs.xyz/docs/publish/integration),
[action](https://hacs.xyz/docs/publish/action), le modèle de PR de `hacs/default` et le README de
`home-assistant/brands`. Le dépôt reste sur le compte personnel `thomasissa-png` (accord du fondateur).

## Checklist

| Exigence HACS | État au 17/10/2026 |
|---|---|
| Dépôt public sur GitHub, ajoutable en dépôt personnalisé | OK (installé ainsi depuis la v0.1.0) |
| Une seule intégration, tout dans `custom_components/calendrier_tempo/` | OK |
| `manifest.json` : domain, documentation, issue_tracker, codeowners, name, version | OK ; `issue_tracker` pointe désormais vers les issues GitHub, version 0.3.0 |
| `hacs.json` avec au moins `name` ; clé `country` si l'intégration vise un pays | OK : `name`, `render_readme`, `homeassistant: 2025.3.0`, `country: ["FR"]` |
| Images de marque : dossier `brand/` avec au moins `icon.png` | OK : `brand/icon.png` (256 x 256) et `brand/icon@2x.png` (512 x 512) |
| Action HACS sans aucune vérification ignorée | OK : `hacs/action@main`, sans `ignore` |
| Action hassfest | OK : `home-assistant/actions/hassfest@master` |
| Workflow lancé à chaque push, chaque PR, tous les jours et à la demande | OK depuis la 0.3.0 (avant : push sur `main` seulement et une fois par semaine) |
| Description du dépôt, issues activées, topics | OK (19 topics, dont `hacs`, `home-assistant`, `edf-tempo`) |
| Licence reconnue par GitHub et approuvée OSI | OK : MIT |
| Dépôt non archivé | OK |
| Au moins une release GitHub complète (pas seulement un tag) | v0.2.0 existe ; **la v0.3.0 reste à publier** |
| Domaine sans conflit avec une intégration du cœur de Home Assistant | OK : `calendrier_tempo` n'existe pas dans le cœur |
| PR ouverte par le propriétaire du dépôt, depuis un compte personnel (PR modifiable) | à faire par Thomas depuis `thomasissa-png` |

Dernière validation sur `main` (v0.2.0, 12/10/2026) : Tests, Hassfest et HACS au vert.
Le workflow utilise maintenant `actions/checkout@v7` et `actions/setup-python@v7` (les v4/v5
déclenchaient l'avertissement « Node.js 20 is deprecated »).

### Marque : plus de PR vers home-assistant/brands

Depuis Home Assistant 2026.3, une intégration personnalisée fournit ses images dans son propre
dossier `brand/` ; le dossier `custom_integrations` de `home-assistant/brands` est désormais
« Legacy » ([annonce du 24/02/2026](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)).
La vérification « brands » de HACS cherche d'abord ce dossier `brand/`. Les images existent déjà
dans le dépôt : aucune image à préparer, aucune PR vers `home-assistant/brands`. Seule limite :
sous Home Assistant 2026.2 ou plus ancien, l'icône ne s'affiche pas (le composant fonctionne).

## Ce qui reste au fondateur

### 1. Fusionner la branche `prix-kwh-0.3.0` dans `main`

Vérifier dans l'onglet Actions que le workflow « Validation » est vert sur `main` (Tests, Hassfest, HACS).

Conseil : publier la release après la mise en production côté serveur des champs `tarif` et
`tarifs` de `/api/today` et `/api/tomorrow`. Avant, le capteur « Prix du kWh actuel » reste
« inconnu » (rien ne casse, mais la nouveauté ne se voit pas).

### 2. Publier la release v0.3.0 (release complète, pas seulement un tag)

```bash
gh release create v0.3.0 --repo thomasissa-png/ha-calendrier-tempo --target main \
  --title "v0.3.0 : prix du kWh et tableau de bord Énergie" --notes-file - <<'EOF'
Nouveautés
- Nouveau capteur « Prix du kWh actuel » (sensor.calendrier_tempo_prix_kwh_actuel), en EUR/kWh TTC : heures pleines de 6 h à 22 h, heures creuses de 22 h à 6 h, couleur de la journée Tempo en cours (celle de la veille entre minuit et 6 h). Utilisable comme « entité avec le prix actuel » dans le tableau de bord Énergie.
- Attributs prix_hp et prix_hc sur les capteurs Couleur aujourd'hui, Couleur actuelle et Couleur demain.
- Les prix viennent de l'API de calendrier-tempo.fr : aucun prix n'est écrit dans l'intégration.
- Signalement des problèmes : issues GitHub du dépôt.

Mise à jour : depuis HACS, puis redémarrez Home Assistant.
EOF
```

### 3. (Facultatif) Mentionner le prix du kWh dans la description du dépôt

```bash
gh repo edit thomasissa-png/ha-calendrier-tempo --description "Intégration Home Assistant (HACS) pour Tempo EDF : couleur du jour et de demain, prévisions EDF Tempo jusqu'à 15 jours (les plus fiables de J+2 à J+5), calendrier des jours blancs et rouges, jours restants, prix du kWh pour le tableau de bord Énergie. API gratuite de calendrier-tempo.fr, sans compte ni clé. Home Assistant integration for EDF Tempo colors, forecasts and kWh price."
gh repo edit thomasissa-png/ha-calendrier-tempo --add-topic energy-dashboard --add-topic prix-kwh
```

### 4. Ouvrir la PR vers `hacs/default`

1. Forker https://github.com/hacs/default avec le compte `thomasissa-png` (pas une organisation).
2. Dans le fork, créer une branche à partir de `master` (ne pas travailler sur `master`).
3. Dans le fichier `integration`, ajouter la ligne suivante **dans l'ordre alphabétique** (sans
   tenir compte des majuscules), entre `"ThomasHFWright/kippy-homeassistant",` et
   `"ThomasLomas/ha-starlinghomehub",` :

   ```
     "thomasissa-png/ha-calendrier-tempo",
   ```

4. Ouvrir la PR. Titre : `Add thomasissa-png/ha-calendrier-tempo`. Ne demander aucune revue
   (le modèle de PR prévient que la PR serait fermée). Corps prêt à coller, après avoir remplacé
   les deux liens `<...>` par ceux de la dernière exécution réussie du workflow « Validation » sur
   `main` (onglet Actions, ouvrir l'exécution, puis les jobs « HACS » et « Hassfest ») :

```markdown
## Checklist

- [x] I've read the [publishing documentation](https://hacs.xyz/docs/publish/start).
- [x] I've added the [HACS action](https://hacs.xyz/docs/publish/action) to my repository.
- [x] (For integrations only) I've added the [hassfest action](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) to my repository.
- [x] The actions are passing without any disabled checks in my repository.
- [x] I've added a link to the action run on my repository below in the links section.
- [x] I've created a new release of the repository after the validation actions were run successfully.

## Links

Link to current release: https://github.com/thomasissa-png/ha-calendrier-tempo/releases/tag/v0.3.0
Link to successful HACS action (without the `ignore` key): <LIEN DU JOB HACS>
Link to successful hassfest action (if integration): <LIEN DU JOB HASSFEST>
```

Conserver la ligne de commentaire `<!-- tid:... -->` du modèle si GitHub la pré-remplit.

### 5. Après la PR

- Délai annoncé par HACS : plusieurs mois. Suivi : https://github.com/hacs/default/pulls (ou la page
  « backlog » citée par la documentation). Si la PR passe en brouillon, corriger puis la remettre
  « Ready for review ».
- Une fois la PR fusionnée : retirer du README l'étape « dépôt personnalisé » (section Installation)
  et mettre à jour la page https://www.calendrier-tempo.fr/domotique.
