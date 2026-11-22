# Guide complet de debrief technique — Minirail

Ce document est fait pour te préparer au debrief technique en profondeur.
Il couvre :
- l'architecture du projet,
- le rôle de chaque fichier,
- ce qui existait avant mes changements,
- ce que j'ai modifié et pourquoi (par livrable),
- les compromis/optimisations possibles,
- une banque de questions-réponses d'entretien.

---

## 1) Vue globale du projet

Minirail est un backend de réservation ferroviaire avec 2 grands domaines :

1. **inventory/** : ce qui est vendu (gares, services, trajets, capacités de sièges)
2. **sales/** : comment on vend (channels/API keys, bookings, tickets, paiements, expiration)

Pile technique :
- FastAPI (HTTP)
- SQLAlchemy 2.0 (ORM)
- PostgreSQL (données + queue Remoulade via pgmq)
- Redis (cache fetchers)
- Remoulade (jobs asynchrones)
- Alembic (migrations)
- Pytest / Ruff / Pyright

---

## 2) Architecture utilisée et pourquoi

### 2.1 Couches logiques

Le code est organisé en couches explicites :

- `api/` : endpoints HTTP (validation d'entrée/sortie + orchestration transaction)
- `jobs/` : logique métier orchestrée (create booking, confirm, cancel, expire)
- `service/` : primitives d'accès/écriture base de données, sans commit
- `fetcher/` : lectures orientées réponse API, parfois cachées
- `models/` : entités ORM
- `schemas/` : schémas Pydantic
- `actors/` : tâches asynchrones (worker)
- `utils/` : transversal (auth, config, app context, erreurs, broker, cache...)

### 2.2 Pourquoi cette architecture

Cette architecture donne :
- **séparation des responsabilités** (API mince, métier testable),
- **testabilité forte** (jobs/services testables sans HTTP),
- **transactions maîtrisées** (`commit` seulement dans API/actors/CLI),
- **évolutivité** (facile d'ajouter des jobs, fetchers, actors).

Un test d'architecture (`tests/architecture/test_layering.py`) enforce ces règles.

### 2.3 Lien avec des architectures “classiques” que tu connais déjà

Si tu as fait des projets MVC / service-repository / hexagonal simplifiée :

- `api/` ≈ Controller
- `jobs/` ≈ Application Service / Use Cases
- `service/` ≈ Repository + data primitives
- `models/` ≈ Domain entities + persistence model
- `schemas/` ≈ DTO

Donc ce n'est pas “exotique” : c'est une variante stricte de clean layering.

---

## 3) Cartographie des fichiers (tous les fichiers code importants)

## Racine
- `README.md` : démarrage local, workflow métier, commandes utiles.
- `ASSIGNMENT.md` : sujet du test (discount codes) et attendus.
- `DESIGN_NOTES.md` : notes de design livrées en PR.
- `pyproject.toml` : dépendances, ruff/pyright config, script CLI `minirail`.
- `Makefile` : commandes `up/migrate/seed/serve/worker/test/lint/typecheck`.
- `docker-compose.yaml` : PostgreSQL + Redis pour dev.
- `configuration_example.yaml` : config par défaut.
- `alembic.ini` : config migrations.
- `Containerfile` : image container (si build).
- `transcripts/cursor-agent-session.md` : transcript agent (livrable demandé).

## alembic/
- `env.py` : branche metadata SQLAlchemy -> Alembic.
- `script.py.mako` : template de migration.
- `versions/0001_initial_schema.py` : schéma initial.
- `versions/0002_booking_expiry_index.py` : index statut/expiration booking.
- `versions/0003_discount_codes.py` : migration discount codes (ajoutée).

## src/minirail/
- `__init__.py` : package marker.
- `asgi.py` : création app FastAPI et montage routes.
- `cli.py` : commandes CLI (`serve`, `worker`, `init-demo-data`, etc.).
- `demo_data.py` : génération data de démonstration.
- `orm.py` : base SQLAlchemy + type UTCDateTime.

### src/minirail/inventory/
- `__init__.py` : package.
- `api/stations.py` : endpoint stations.
- `api/trips.py` : endpoint search trips.
- `fetcher/station.py` : lecture stations.
- `fetcher/trip_search.py` : lecture résultat recherche trajet + cache.
- `models/station.py` : gare.
- `models/route.py` : ligne commerciale.
- `models/service.py` : circulation d'un train/date + status.
- `models/leg.py` : segment de trajet.
- `models/od.py` : Origin-Destination vendable (peut couvrir plusieurs legs).
- `schemas/station.py` : sortie station.
- `schemas/trip.py` : sortie recherche trajet.
- `service/seat_inventory.py` : hold/release sièges atomique.

### src/minirail/sales/
- `__init__.py` : package.
- `actors/booking_expiry.py` : actor expiration booking.
- `actors/notifications.py` : actor notifications (stub logique).
- `api/bookings.py` : endpoints booking create/get/confirm/cancel.
- `fetcher/booking.py` : lecture booking détaillé.
- `fetcher/sales_channel.py` : lookup channel/API key.
- `jobs/create_booking.py` : réservation PENDING + hold sièges.
- `jobs/confirm_booking.py` : paiement + confirmation.
- `jobs/cancel_booking.py` : annulation + libération sièges.
- `jobs/expire_booking.py` : expiration auto + libération sièges.
- `models/booking.py` : entité booking (status lifecycle).
- `models/passenger.py` : passager booking.
- `models/ticket.py` : ticket passager/OD.
- `models/sales_channel.py` : distributeur (API key).
- `models/discount_code.py` : promo code (ajouté).
- `schemas/booking.py` : input/output booking API.
- `schemas/sales_channel.py` : schémas channel.
- `service/booking.py` : primitives DB booking.
- `service/discount_code.py` : primitives DB code promo (ajouté).

### src/minirail/utils/
- `api.py` : session transaction dependency + gestion exceptions API.
- `app.py` : app context global (engine, session_factory, redis, logger...).
- `auth.py` : validation API key / current sales channel.
- `broker.py` : config Remoulade broker.
- `config.py` : chargement config YAML/env.
- `date_utils.py` : `utc_now()` etc.
- `exc.py` : exceptions métier -> error codes HTTP.
- `fetcher.py` : base fetchers SQL/Redis.
- `job.py` : base class jobs + result pattern.
- `notifier.py` : abstraction notifications.
- `payments.py` : faux provider paiement.
- `redis.py` : client redis wrapper.
- `schema.py` : base Pydantic camelCase/forbid extra.

## tests/
- `conftest.py` : harness DB transactionnel + fake redis + stub broker.
- `factories.py` : factories factory-boy des entités.
- `helpers.py` : builders de graphes de données test.
- `architecture/test_layering.py` : garde-fous d'architecture.
- `inventory/test_*` : tests inventory.
- `sales/test_create_booking.py` : création booking.
- `sales/test_confirm_booking.py` : confirmation.
- `sales/test_cancel_booking.py` : annulation.
- `sales/test_expire_booking.py` : expiration.
- `sales/test_discount_codes.py` : tests discount (ajouté).
- `utils/test_*` : auth, cache, healthcheck, isolation.

---

## 4) Flux métier de bout en bout (important pour debrief)

## 4.1 Search trip
1. Client appelle `/api/trips/search`
2. API valide params
3. Fetcher compose query SQL (OD + legs + disponibilité)
4. Réponse listant ODs vendables

## 4.2 Create booking (avant discount)
1. API `/api/bookings/`
2. `CreateBookingJob` :
   - charge OD bookable,
   - `hold_seats(...)` atomique sur legs couverts,
   - crée Booking(PENDING)+Passengers+Tickets(HELD),
   - set `expires_at`.
3. API commit transaction.
4. API envoie message différé `expire_booking` (TTL).

## 4.3 Confirm booking
1. API `/confirm`
2. `ConfirmBookingJob` :
   - vérifie status PENDING et non expiré,
   - appelle `payments.charge`,
   - passe booking/tickets en CONFIRMED.
3. Commit + actor notification.

## 4.4 Cancel booking
1. API `/cancel`
2. `CancelBookingJob` :
   - si PENDING/CONFIRMED,
   - passe booking CANCELLED + tickets CANCELLED,
   - release seats.
3. Commit + notification + invalidation cache trip search.

## 4.5 Expiration booking
Actor différé exécute `ExpireBookingJob` :
- si toujours PENDING et `expires_at` passé,
- passe EXPIRED + release seats.

---

## 5) Ce que j'ai modifié (avant/après) — par livrable

## Livrable 1 — Modèle et migration

### Fichiers
- `src/minirail/sales/models/discount_code.py` (nouveau)
- `src/minirail/sales/models/booking.py`
- `src/minirail/sales/models/__init__.py`
- `alembic/versions/0003_discount_codes.py` (nouveau)

### Avant
- Aucun concept de promo code.
- Booking avait juste `total_amount`, `currency`, etc.

### Après
- Nouveau modèle `DiscountCode` :
  - `sales_channel_id`, `code`, `percent_off`, `max_uses`, `use_count`, `is_active`.
  - contrainte unicité `(sales_channel_id, code)`.
- Booking enrichi :
  - `discount_code_id` nullable (FK),
  - `discount_amount` (Decimal) pour tracer la remise.
- Migration SQL :
  - création table `discount_code`,
  - ajout colonnes booking,
  - ajout FK,
  - backfill `discount_amount` via default puis cleanup default.

### Raisonnement bas niveau
- On sépare `discount_code` dans sa table (évite de surcharger booking).
- `discount_amount` stocké pour audit (même si code change plus tard).
- Unicité par channel pour éviter collisions cross-partner.

---

## Livrable 2 — Service métier discount + erreurs API

### Fichiers
- `src/minirail/sales/service/discount_code.py` (nouveau)
- `src/minirail/utils/exc.py`

### Avant
- Pas d'erreur dédiée discount.

### Après
- Nouvelles erreurs API stables :
  - `INVALID_DISCOUNT_CODE` (HTTP 400)
  - `DISCOUNT_CODE_EXHAUSTED` (HTTP 409)
- Service discount avec primitives :
  - `get_discount_code_for_update(...)` avec `SELECT ... FOR UPDATE`,
  - `compute_discount_amount(...)`,
  - `reserve_discount_use(...)`,
  - `release_discount_use(...)`.

### Raisonnement bas niveau
- Le lock SQL évite le race condition (`use_count` > `max_uses`).
- `ROUND_HALF_UP` pour comportement monétaire classique.
- Service sans commit pour respecter architecture.

---

## Livrable 3 — Intégration au flux booking

### Fichiers
- `src/minirail/sales/schemas/booking.py`
- `src/minirail/sales/service/booking.py`
- `src/minirail/sales/jobs/create_booking.py`
- `src/minirail/sales/jobs/cancel_booking.py`
- `src/minirail/sales/jobs/expire_booking.py`
- `src/minirail/sales/api/bookings.py`
- `src/minirail/sales/fetcher/booking.py`

### Avant
- `BookingCreateSchema` sans `discountCode`.
- create job calculait total = prix OD * nb passagers.
- cancel/expire ne manipulaient aucun usage de code.

### Après
- Request create accepte `discountCode` optionnel.
- `CreateBookingJob` :
  - valide code pour le sales channel,
  - calcule réduction,
  - réserve usage (`use_count += 1`),
  - écrit `discount_code_id` et `discount_amount`.
- `CancelBookingJob` :
  - si annulation depuis PENDING -> release usage.
  - si annulation depuis CONFIRMED -> usage conservé.
- `ExpireBookingJob` :
  - release usage (comme release seats) si PENDING expiré.
- Response booking expose :
  - `discountAmount`,
  - `discountCode` (string).

### Raisonnement bas niveau
- Réserver à la création garantit qu'on ne dépasse pas la promesse partenaire.
- Libérer sur non-paiement (cancel pending / expire) reflète vraie “consommation”.
- Conserver sur cancel confirmé = la réduction a déjà servi.

---

## Livrable 4 — CLI et seed

### Fichiers
- `src/minirail/cli.py`
- `src/minirail/demo_data.py`

### Avant
- Pas de commande création code promo.
- Seed ne créait pas de code.

### Après
- Nouvelle commande :
  - `minirail create-discount-code CHANNEL CODE --percent-off X --max-uses N`
- Seed demo crée `SAVE10` (10%, 100 uses).
- CLI seed affiche le code demo.

### Raisonnement
- Respect du style existant : admin simple via CLI.
- Démo utilisable immédiatement sans setup manuel.

---

## Livrable 5 — Tests

### Fichiers
- `tests/sales/test_discount_codes.py` (nouveau)
- `tests/factories.py`
- `tests/sales/conftest.py`
- (petits ajustements format/type dans `cli.py`, `sales/service/booking.py`, `sales/fetcher/booking.py`)

### Cas testés
- application correcte du discount,
- code épuisé,
- code inconnu,
- code d'un autre sales channel,
- release usage sur cancel pending,
- release usage sur expire pending,
- conservation usage sur confirm puis cancel.

### Pourquoi ces tests
- Ils couvrent les invariants métier critiques.
- Ils protègent contre les regressions du cycle de vie booking.

---

## Livrable 6 — Documentation deliverables test

### Fichiers
- `DESIGN_NOTES.md`
- `transcripts/cursor-agent-session.md`

Rôle : satisfaire explicitement les livrables de `ASSIGNMENT.md`.

---

## 6) Complexité et performance

## 6.1 Complexité principale
- `hold_seats/release_seats` : O(nombre de legs couverts par OD)
- create booking : O(passagers + legs couverts)
- fetch booking : O(passagers + tickets)

## 6.2 Concurrence
Point sensible = usage discount en parallèle :
- résolu par lock row-level `FOR UPDATE`.

## 6.3 Optimisations possibles (si on te challenge)
1. **Validation period** (start/end at) avec index.
2. **Counter matérialisé par table redemptions** au lieu de `use_count`.
3. **Idempotency key** côté create booking.
4. **Historique discount par booking** plus détaillé (reason codes).
5. **Stratégie optimistic lock** (`version`) vs `FOR UPDATE`.

---

## 7) Questions de debrief probables + réponses

## Architecture
1. **Pourquoi jobs + service ?**
   - Jobs orchestrent la logique métier ; services font primitives DB réutilisables.
2. **Pourquoi pas commit dans jobs ?**
   - Atomicité contrôlée au niveau caller (API/actor/CLI), pattern cohérent testable.
3. **Pourquoi fetcher séparé ?**
   - Couches lecture spécialisées, facilement cachables.

## Discount design
4. **Pourquoi réserve d'usage à la création ?**
   - Empêche oversubscription lorsque plusieurs utilisateurs tentent le même code.
5. **Pourquoi release seulement si booking non confirmé ?**
   - Le promo est “consommé” sur une vente payée.
6. **Pourquoi code unique par channel ?**
   - Un partenaire peut avoir un code `SAVE10` sans conflit global.

## Data/DB
7. **Pourquoi stocker `discount_amount` sur booking ?**
   - Audit immuable de ce qui a été appliqué à l'instant T.
8. **Pourquoi Decimal et pas float ?**
   - Exactitude monétaire.
9. **Pourquoi `FOR UPDATE` plutôt qu'un update conditionnel ?**
   - Simplicité et robustesse ; l'alternative `UPDATE ... WHERE use_count < max_uses` est possible.

## API/Tests
10. **Pourquoi 400 pour invalid code et 409 pour exhausted ?**
    - 400 = entrée invalide ; 409 = conflit d'état métier.
11. **Pourquoi ajouter `discountCode` dans output ?**
    - Transparence client (trace de promo appliquée).
12. **Pourquoi ces tests et pas seulement happy path ?**
    - Les bugs viennent souvent des bords de cycle de vie, pas du cas nominal.

---

## 8) Questions de critique / optimisation avancée

1. **Comment éviter hotspots sur un code ultra populaire ?**
   - sharding logique de codes, queue, ou approche update conditionnel atomique.
2. **Et si on veut plafonner remise max en euros ?**
   - ajouter colonne `max_discount_amount` et `min()` au calcul.
3. **Et si le code devait expirer à date ?**
   - colonnes `valid_from/valid_until` + validation + index composite.
4. **Stacking de codes ?**
   - table pivot booking_discount, règles de priorité/composition.

---

## 9) Plan de préparation entretien (conseillé)

1. Refaire à la main le flux : search -> create -> confirm -> cancel -> expire.
2. Expliquer verbalement chaque couche (`api/jobs/service/fetcher/models/schemas`).
3. Dessiner le schéma DB simplifié :
   - sales_channel 1..N booking
   - booking 1..N passenger / 1..N ticket
   - booking N..1 discount_code (optionnel)
4. Préparer 3 compromis :
   - simplicité vs extensibilité,
   - lock pessimiste vs optimiste,
   - stocker `use_count` vs redemptions détaillées.
5. Réviser tous les commits dans l'ordre.

---

## 10) Limite importante sur “recherches Wiremind”

Je n'ai pas de source interne privée Wiremind dans cet environnement.
Je ne peux donc pas garantir “les questions exactes” de leurs debriefs passés.
En revanche, la banque de questions ci-dessus est alignée avec :
- l'énoncé ASSIGNMENT,
- le type d'architecture présente,
- les points que les intervieweurs challengent typiquement sur ce genre de test.

Si tu veux, je peux faire ensuite une **simulation d'entretien complète** en mode Q/R (interviewer vs toi) avec correction détaillée de tes réponses.
