# Architecture et choix techniques

## Deux sources, un parcours utilisateur

Les deux sources ont leurs propres modules de collecte, filtrage, scoring et stockage. Cette
séparation conserve leurs particularités : API de recherche paginée pour AP-HP, API WordPress
et taxonomies pour HCL. Le dashboard normalise les colonnes pour proposer une interface commune.

Un traitement suit l'ordre collecte → stockage → règles métier → filtre LLM → scoring. Le
profil privé et certains feedbacks alimentent le scoring. Le score sert à classer les offres,
pas à estimer une probabilité de recrutement calibrée.

## Cycle de vie des offres

- Un identifiant source inconnu crée une offre active.
- Une offre retrouvée remet son compteur d'absence à zéro.
- Cinq collectes complètes consécutives sans l'offre la marquent `removed` ; aucune suppression
  physique n'est nécessaire pour ce suivi.
- Si l'offre revient, elle redevient active.

Les collecteurs vérifient les totaux et la pagination avant de fournir une liste utilisable.
Une page manquante, un dépassement de la limite AP-HP ou une offre impossible à normaliser
interrompt la collecte, afin qu'un résultat partiel ne soit pas interprété comme des retraits.
Une modification du site pendant la pagination peut donc demander une nouvelle exécution.

L'identifiant AP-HP est désormais indépendant de la présence d'une référence dans la description.
Les identifiants historiques `ID_<id>` déjà en base sont conservés pour ne pas détacher leurs
feedbacks ou candidatures. Les éventuels doublons préexistants ne sont pas fusionnés automatiquement.

## Persistance et reprise

Le schéma PostgreSQL se trouve dans [`sql/schema.sql`](../sql/schema.sql). Les tables `jobs`
et `hcl_jobs` stockent les offres et leurs analyses ; les tables de feedback et de candidatures
conservent les choix utilisateur. `pipeline_runs` stocke les compteurs, le statut et la durée.

Les étapes ne constituent pas une transaction unique : une collecte réussie reste enregistrée
si une analyse échoue ensuite. Les offres non filtrées et les offres retenues sans score sont
reprises au prochain lancement. Les erreurs et quotas sont comptabilisés ; une exécution
incomplète échoue au niveau du pipeline et du workflow GitHub Actions.

L'initialisation crée les tables absentes et ajoute deux colonnes historiques AP-HP manquantes.
Ce n'est pas un outil général de migration : sauvegarder une ancienne base et comparer ses types,
colonnes et contraintes avant de réutiliser cette version.

## Confidentialité

Le code et les exemples de profils sont publics. Les profils réels, les feedbacks, les
candidatures et les résultats personnalisés restent dans l'environnement privé et la base.
Les prompts sont envoyés à Groq ; les notifications configurées passent par Telegram.

Le dashboard vérifie un mot de passe avant tout accès aux données. Cette protection simple
n'est pas une authentification multi-utilisateur : pour un déploiement public, prévoir une
authentification adaptée, TLS et des contrôles réseau. Les messages d'erreur évitent le texte brut
des exceptions DB/API, susceptible de contenir un jeton ou du contenu privé.

## Limites connues

- Les règles et une partie des prompts reflètent un profil ingénieur généraliste Bac+5.
- Les contenus déjà connus ne sont pas systématiquement réanalysés après modification d'une offre.
- Les limites et erreurs des services externes peuvent retarder le traitement.
- Les tests actuels sont hors réseau, avec doubles de services et données synthétiques ;
  un test bout en bout PostgreSQL/Groq/Telegram reste nécessaire avant mise en production.
- Le dashboard reste un module volumineux : une séparation en pages et services est une prochaine
  amélioration possible, indépendante de ce nettoyage.
