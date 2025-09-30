# Vehicle Reservations

A Django-based vehicle rental/reservation system with user accounts, search & pricing, carts, reservation groups, manager/admin workflows, email notifications, WebSocket updates (Django Channels), and a mock payment flow.

---

## Table of contents

* [Overview](#overview)
* [What makes this project stand out](#what-makes-this-project-stand-out)
* [Core features](#core-features)
* [Domain model](#domain-model)
* [Status lifecycle & permissions](#status-lifecycle--permissions)

  * [Location loop (fleet rebalancing)](#location-loop-fleet-rebalancing)
* [Search, availability & pricing](#search-availability--pricing)
* [Carts & checkout](#carts--checkout)

  * [Cart → unpaid reservation edge case](#cart--unpaid-reservation-edge-case)
* [Emails](#emails)
* [Real-time updates (Channels)](#real-time-updates-channels)
* [Mock payments](#mock-payments)
* [Admin & manager tooling](#admin--manager-tooling)
* [Project structure](#project-structure)
* [Local setup](#local-setup)
* [Configuration](#configuration)
* [Run the app](#run-the-app)
* [URL map (high level)](#url-map-high-level)
* [Development notes](#development-notes)
* [Registration & pending profile expiry](#registration--pending-profile-expiry)

---

## Overview

Users can search vehicles by location and dates, see live availability windows, and add one or more vehicles into a **Reservation Group**. Managers/admins review groups, approve/reject them, and once approved the user pays via a **mock payment** page. The system sends email updates and broadcasts real-time events over WebSockets (Channels). Pricing supports discounts for multi-week/month rentals.

---

## What makes this project stand out

* **Real availability, not guesses** — Searches exclude conflicts from both **existing reservations** *and* the user’s **cart**, so results don’t fall apart at checkout.
* **Smart pricing engine** — Transparent day/week/month packing with best-of cost selection and an itemized breakdown users can trust.
* **Fleet rebalancing ("location loop")** — Automatic pickup/return allowance flips on completion model real fleet circulation with zero manual ops.
* **Robust edge-case handling** — From abandoned sign-ups (auto resend + TTL reset) to editing unpaid reservations (safe re-quoting + new intents).
* **Race-condition aware** — Heavy use of `transaction.on_commit`, `select_for_update`, and DB constraints means side effects only fire after successful commits.
* **Data snapshots for durability** — Reservation rows keep human-readable snapshots (vehicle and locations) so history still renders even if the source objects are later modified or deleted.
* **Operational guardrails** — Constraints like **one active cart per user**, seat bounds by vehicle type, positive pricing, and legal status transitions prevent bad states by construction.
* **Real-time UX** — WebSocket broadcasts for group/reservation events keep dashboards and user pages live without polling.

---

## Core features

* **Authentication & profiles** (register, verify email via code, login, profile edit/change password).
* **Search** with date & location filters; excludes conflicts from existing reservations and items in the user’s cart.
* **Quote/pricing engine** with month/week/day discount rules and transparent breakdowns.
* **Reservation Groups** containing user’s **Vehicle Reservations**, with a clear status lifecycle.
* **Cart** → **Checkout** converts items into a reservation group.
* **Manager/Admin** dashboards and actions (approve, reject, promote/demote users, block/unblock).
* **Emails** on group creation/status changes and reservation edits/add/remove (text + optional HTML).
* **WebSockets (Django Channels)** broadcasting reservation/group events.
* **Mock payment** flow with predictable success/failure outcomes.

---

## Domain model

**inventory.models.reservation**

* `Location`: pickup/return points.
* `ReservationStatus` (enum): `PENDING`, `AWAITING_PAYMENT`, `RESERVED`, `REJECTED`, `CANCELED`, `COMPLETED`.

  * `ReservationStatus.blocking()` returns statuses that block inventory.
* `ReservationGroup`: top-level container for a user’s reservations; tracks status; optional short `reference`.
* `VehicleReservation`: a single vehicle + (start, end) + pickup/return locations + optional `total_price`.

**inventory.models.vehicle**

* `Vehicle`: has `price_per_day` and M2M relations for allowed pickup/return locations.

Relationships:

* A `ReservationGroup` **has many** `VehicleReservation`.
* A `VehicleReservation` **belongs to** `Vehicle`, `pickup_location`, `return_location`, and a `user`.

---

## Status lifecycle & permissions

### Transition rules (`inventory.views.status_switch`)

* **approve** → `AWAITING_PAYMENT` (from `PENDING`, **staff only**)
* **reject** → `REJECTED` (from `PENDING`, **staff only**, cancels payment intents)
* **cancel** → `CANCELED` (from `PENDING` or `AWAITING_PAYMENT`, **owner or staff**, cancels intents)
* **complete** → `COMPLETED` (from `AWAITING_PAYMENT`, **staff only**)

Editing rules (selected views):

* Users can edit their own reservations. Admin/Manager can edit any.
* Cannot modify a group in `RESERVED`, `REJECTED`, or `CANCELED`.
* Deleting the **last** item in a group is disallowed.

On transition to **COMPLETED**, signals update vehicle availability:

* Pickup allowed at what used to be the **return** location.
* Returns allowed at what used to be the **pickup** location.

### Location loop (fleet rebalancing)

To avoid vehicles getting “stuck” at a single branch, when a **Reservation Group** moves to **COMPLETED** we flip per-vehicle location allowances:

* If a vehicle was **picked up** at `A` and **returned** to `B`, then on completion:

  * `A` is added to the vehicle’s **allowed return** locations.
  * `B` becomes the vehicle’s **allowed pickup** location.
* This is applied in one pass for all items in the group (`ReservationGroup.apply_vehicle_location_flip`) and happens **after** the transaction commits.

**Why this matters:** it creates a natural **location loop** that models fleet circulation without manual rebalance tasks, and future searches will reflect the new pickup/return options immediately.

---

## Search, availability & pricing

### Availability

* Search takes `start`, `end`, optional `pickup_location`, `return_location`.
* Candidate vehicles must have at least one pickup and one return location (optionally filtered by chosen ones).
* Busy blocks = reservations in **blocking** statuses + the current user’s **cart** items that overlap the range.
* Free windows are computed from the requested range minus merged busy blocks (`inventory.helpers.intervals.free_slices`).

### Pricing (`inventory.helpers.pricing`)

* Input: `(start_date, end_date, RateTable(day=<float>, currency="EUR"))`.
* **Discount rules:**

  * **Month blocks**: every 30 days are billed as **26 day-units**.
  * **Week blocks**: **1 free day per week**, up to **3 total free days**.
* The algorithm computes **month-first** and **week-first** packings and picks the cheaper.
* Output includes total days, total price, currency, and a detailed breakdown (month/week/day lines).

---

## Carts & checkout

* Users add a vehicle slice to the **cart** (`cart.models.cart.CartItem`). Validation merges compatible items and prevents bad ranges or locations.
* **Checkout** locks the cart & vehicles, checks for conflicts, and:

  * reuses an existing group in `PENDING`/`AWAITING_PAYMENT` or creates a new `PENDING` group,
  * creates corresponding `VehicleReservation` rows,
  * computes `total_price` per reservation via the pricing helper,
  * marks the cart as checked out and clears items.

### Cart → unpaid reservation edge case

It’s valid to add vehicles **after** checkout if the group is **not yet paid**:

* **Editable states:** groups in `PENDING` or `AWAITING_PAYMENT` can accept new reservations; `RESERVED`, `REJECTED`, and `CANCELED` cannot.
* **How it works:**

  1. User adds a slice to the **Cart**; cart validation merges adjacent/touching ranges and prevents overlaps per vehicle.
  2. **Checkout** reuses the user’s latest group in `PENDING`/`AWAITING_PAYMENT` **or** creates a fresh `PENDING` group.
  3. New `VehicleReservation` rows are created; totals are recalculated.
  4. If a **PaymentIntent** already exists for the group:

     * mark the old intent **expired/canceled** (so amounts don’t mismatch),
     * create a **new PaymentIntent** with the updated amount (group sum in cents).
* **Concurrency safety:** cart item merges/selects use `select_for_update()` inside a transaction; availability checks consider **blocking** statuses (`PENDING`, `AWAITING_PAYMENT`, `RESERVED`) to avoid double-booking.

---

## Emails

Helpers in `emails.helpers` + senders in `emails.send_emails`:

* **Group created** (`reservation_created`)
* **Group status changed** (`reservation_confirmed` / `reservation_rejected` / fallback `reservation_status_changed`)
* **Reservation edited** (`reservation_edited` with diff of key fields)
* **Vehicle added** (`vehicle_added`) / **Vehicle removed** (`vehicle_removed`)

Text templates are required; HTML templates are optional (graceful fallback).

`DEFAULT_FROM_EMAIL` is used if configured; otherwise falls back to `no-reply@example.com`.

---

## Real-time updates (Channels)

Signals (`inventory.views.signals`) broadcast events to Channels groups:

* Global group: `reservations.all`
* Events (type: `reservation.event`):

  * `group.created`, `group.status_changed` with `{kind:"group", group_id, status, changed_at}`
  * `reservation.created`, `reservation.updated`, `reservation.deleted` with fields like `{kind:"reservation", id, group_id, vehicle_id, start_date, end_date, status, changed_at}`

Side effects fire **on transaction commit** to avoid race conditions.

---

## Mock payments

App: `mockpay`

* **PaymentIntent** with `amount` (cents), `currency`, `client_secret`, `status`, and expiry logic.
* Create intent from a group in `AWAITING_PAYMENT`. Amount is the sum of reservation `total_price` values (converted to cents).
* **Checkout page** (`mockpay:checkout_page`) simulates card processing.

  * **Auto outcomes** by PAN:

    * `4242 4242 4242 4242` → **success**
    * `4000 0000 0000 0002` → **fail**
    * any other → **success**
  * Or explicitly choose outcome (`success` / `fail` / `cancel`) via the form.
* On **success**:

  * Intent → `SUCCEEDED`
  * Group → `RESERVED`
* On **fail**/**cancel**:

  * Intent → `FAILED`/`CANCELED`
* Expiry sets status to `EXPIRED` and shows a retry message.

Helpers in `mockpay.helpers` format cents ↔︎ EUR strings and handle Decimal rounding.

---

## Admin & manager tooling

**accounts.views.admins_managers**

* Admin dashboard: user list + filters (role, blocked).
* Actions: block/unblock users, promote/demote between `user` and `manager`, create/edit/delete users (never modify other admins).
* Manager dashboard: list vehicles and reservations (role-gated).
* Per-view permission decorators enforce role and Django permissions.

**accounts.views.vehicles / locations**

* CRUD for `Vehicle` and `Location`, with safety checks (e.g., cannot delete a location/vehicle participating in a **blocking** reservation).

---

## Project structure

*Only key parts shown.*

```
accounts/
  views/
    auth.py                # register/login/verify email, profile, password reset
    admins_managers.py     # admin & manager dashboards + actions
    vehicles.py            # vehicle CRUD (manager/admin)
    locations.py           # location CRUD (manager/admin)
    reservations.py        # reservation list + group status actions (manager/admin)
    helpers.py             # email code issuance/validation, email senders
cart/
  models/                  # Cart, CartItem
  views.py                 # add_to_cart, view_cart, checkout, remove_from_cart
emails/
  helpers.py               # render_pair, recipients, change detection
  send_emails.py           # concrete email sending for events
inventory/
  helpers/
    intervals.py           # merge/free slice utils
    pricing.py             # RateTable, quote_total (discount rules)
    parse_iso_date.py
    redirect_back_to_search.py
  models/
    reservation.py         # Location, ReservationGroup, VehicleReservation, ReservationStatus
    vehicle.py             # Vehicle
  views/
    search.py              # home & search (availability + quotes)
    reservation_actions.py # All the actions with reservations (Reject, Complete, Approve etc.)
    status_switch.py       # transition_group (approve/reject/cancel/complete)
    signals.py             # post/pre-save hooks and websocket/email side effects
mockpay/
  forms.py
  helpers.py               # money helpers
  models.py                # PaymentIntent (+ status enum)
  views.py                 # create intent, checkout, result/success pages
```

---

## Local setup

### Requirements

* Python 3.11+
* PostgreSQL or SQLite (dev)
* Redis (recommended for Channels in real deployments; dev can use in-memory)

### Installation

```bash
# 1) Create & activate a venv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install deps
pip install -r requirements.txt  # or pip install django channels

# 3) Create env file (see "Configuration")
cp .env.example .env  # if provided, otherwise create manually

# 4) Migrate DB
python manage.py migrate

# 5) Create a superuser
python manage.py createsuperuser

# 6) (Optional) Load sample data if fixtures are provided
# python manage.py loaddata sample_data.json
```

---

## Configuration

Set environment variables or `settings.py` values as needed:

* **Django**

  * `SECRET_KEY`
  * `DEBUG` (True/False)
  * `ALLOWED_HOSTS`
* **Email**

  * `DEFAULT_FROM_EMAIL`
  * `EMAIL_BACKEND` (e.g., `django.core.mail.backends.console.EmailBackend` for dev)
* **Channels**

  * `CHANNEL_LAYERS` (dev: in-memory; prod: Redis)
* **Database**

  * `DATABASE_URL` or individual `ENGINE/NAME/USER/PASSWORD/HOST/PORT`

For local development, a minimal `.env` might look like:

```env
DEBUG=1
SECRET_KEY=dev-secret-change-me
ALLOWED_HOSTS=*

# Email (console backend prints emails to the terminal)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=no-reply@example.com
```

---

## Run the app

**Django dev server (ASGI for Channels):**

```bash
python manage.py runserver
```

For production-like Channels serving, use Daphne/Uvicorn:

```bash
# Example with daphne
daphne config.asgi:application -p 8000
```

> Ensure `ASGI_APPLICATION` is set (usually `config.asgi.application`) and `CHANNEL_LAYERS` configured.

---

## URL map (high level)

* `/` — home/search
* `/inventory/reservations/` — my reservations (groups split into active/archived)
* `/inventory/reserve/` — POST create/add item into a group
* `/inventory/reservations/<group_id>/approve` — POST (staff)
* `/inventory/reservations/<group_id>/reject` — POST (staff)
* `/inventory/reservations/<group_id>/cancel` — POST (owner/staff)
* `/inventory/reservation/<pk>/edit` — GET/POST edit reservation
* `/inventory/reservation/<pk>/delete` — POST delete reservation
* `/cart/` — view cart
* `/cart/add` — POST add to cart
* `/cart/checkout` — POST convert to reservation group
* `/mockpay/intent/<group_id>/create` — POST create payment intent
* `/mockpay/checkout/<client_secret>` — GET/POST checkout
* `/mockpay/result/<client_secret>` — GET outcome page
* `/accounts/...` — register, verify email, login/logout, profile, admin/manager dashboards, etc.

*(Exact patterns depend on your `urls.py`, but the above mirrors the view names and redirects used in code.)*

---

## Development notes

* **Signals** defer side effects with `transaction.on_commit` to avoid emails/broadcasts for rolled-back transactions.
* **Validation**:

  * Cart items and reservation edits check date order, “not in the past,” location allowances, and conflict overlaps (`ReservationStatus.blocking()`).
  * Attempts to mutate groups in final states are blocked early with user-friendly messages.
* **Emails**: templates live under `templates/emails/<kind>/<kind>.txt|.html`. If an HTML template is missing, the text email still sends.
* **Pricing**: only `RateTable.day` is used by current logic; `week`/`month` fields exist for future extension.
* **Security**: admin-to-admin modifications are intentionally prevented in several views.

---

## Registration & pending profile expiry

During registration we create a **PendingRegistration** (24h TTL) and send a verification code by email.

* **Re-login within 24h (abandoned sign-up edge case):**
  If a user abandons registration and later tries to **log in** within 24 hours using the same username/email, we **issue a fresh verification code** and **recreate** the pending record with a new `expires_at` (24h from that moment). Practically: the user can just come back, log in, and a brand-new code arrives—no need to start over manually.

* **Expired pending:**
  After 24h the pending record is purged; the user must start registration again.

> Implementation notes: `PendingRegistration.start(...)` deletes any existing pending rows for the same username/email, then creates a new one with `expires_at = now() + 24h`, ensuring a clean reset and a new code each time.
