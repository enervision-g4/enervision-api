# Documentation d'enervision-api

Cette documentation explique le projet `enervision-api` en partant de zéro : elle ne
suppose aucune connaissance préalable de FastAPI, de JWT ou des WebSockets. Elle est
complémentaire du [README.md](../README.md) à la racine du dépôt, qui reste la référence
rapide pour installer et lancer le projet ; ici, l'objectif est de comprendre
**pourquoi** le code est écrit comme il l'est.

## Par où commencer

Les fichiers sont numérotés dans l'ordre de lecture conseillé :

1. **[01-introduction.md](01-introduction.md)** — Le rôle de l'API dans le projet
   EnerVision, et le vocabulaire de base (REST, JWT, CORS, WebSocket) pour qui n'est pas
   familier de ces notions.
2. **[02-architecture.md](02-architecture.md)** — Organisation du code, montage des
   routers, et le rôle de chaque module.
3. **[03-modele-de-donnees.md](03-modele-de-donnees.md)** — Les tables lues par l'API
   (miroir du schéma créé par `enervision-devops`) et les schémas de réponse.
4. **[04-routes-rest.md](04-routes-rest.md)** — Le détail de chaque route HTTP : sites,
   mesures, alertes, prédictions, recommandations.
5. **[05-temps-reel-websocket.md](05-temps-reel-websocket.md)** — Le mécanisme de flux
   temps réel (`/ws/readings`, `/ws/alerts`) : pourquoi il existe, comment il évite de
   rejouer l'historique, et le bug de charge CPU qu'il corrige.
6. **[06-securite.md](06-securite.md)** — Authentification JWT, hachage Argon2id, et
   pourquoi CORS est configuré comme il l'est.
7. **[07-configuration.md](07-configuration.md)** — Toutes les variables
   d'environnement, ce qu'elles font et qui les utilise.
8. **[08-deploiement-et-flux-devops.md](08-deploiement-et-flux-devops.md)** — Comment
   l'image est construite, puis déployée via le workflow réutilisable
   d'`enervision-devops` : le flux complet, du `git push` au conteneur qui tourne.
9. **[09-tests-et-qualite.md](09-tests-et-qualite.md)** — Comment vérifier que le code
   fonctionne : tests automatiques, vérificateurs de style et de types.

## En une phrase

`enervision-api` est une API FastAPI qui lit dans TimescaleDB les données produites par
`enervision-etl` (sites, mesures, alertes) et `enervision-ml` (prédictions,
recommandations), les protège derrière une authentification JWT, et les expose au
dashboard aussi bien en REST paginé qu'en flux temps réel par WebSocket.
