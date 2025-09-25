# 🚗 Vehicle Reservations Platform

A Django-based web application for managing vehicle rentals with support for admins, managers, and users.
Includes a web dashboard, REST API (via Django Ninja), and a mock payment system.
<br />


📖 Features

User Roles

* 👤 Users – register, log in, make reservations, view their bookings

* 🛠 Managers – manage vehicles, reservations, and locations

* 🛡 Admins – manage users, managers, and all system operations

Reservation System

* Make reservations for vehicles with pickup/return locations

* Group reservations with approval/rejection by managers/admins

* Automatic price calculation per day

Vehicles

* Different types (Car, Motorcycle, Caravan, Van, Truck)

* Engine types (Petrol, Diesel, Electric, Hybrid)

* Seat validation (or unlimited seats for Golf MK2 😉)

Locations

* Manage pickup & return locations

Dashboards

* Admin dashboard (manage users, stats, reservations)

* Manager dashboard (manage vehicles, reservations, locations)

Mock Payment

* “MockPay” app simulates a checkout/payment flow

API

* Fully documented API using Django Ninja & Swagger UI

* Basic Authentication support
<br />


🛠 Tech Stack

* Backend: Python, Django, Django Ninja

* Database: PostgreSQL (preferred) or SQLite (dev mode)

* Frontend: Django templates (HTML, CSS)

* Docs: Swagger UI (/api/docs) + Redoc (/api/redoc)
<br />


⚙️ Setup Instructions
1. Clone the repo
*     git clone https://github.com/your-org/vehicle-reservations.git
      cd vehicle-reservations
2. Create virtual environment & install dependencies
*     python -m venv .venv
      source .venv/bin/activate   # On Windows: .venv\Scripts\activate
      pip install -r requirements.txt
3. Configure environment variables

Create a .env file in the root folder:

*      SECRET_KEY=your-secret-key
          DEBUG=True
          POSTGRES_DB=vehiclerental
          POSTGRES_USER=postgres
          POSTGRES_PASSWORD=postgres
          POSTGRES_HOST=localhost
          POSTGRES_PORT=5432
          EMAIL_HOST=smtp.gmail.com
          EMAIL_PORT=587
          EMAIL_HOST_USER=you@example.com
          EMAIL_HOST_PASSWORD=yourpassword
          EMAIL_USE_TLS=true
4. Run migrations & create admin and manager
*     python manage.py makemigrations
      python manage.py migrate
      python manage.py create_admin
      python manage.py create_manager
5. Start the server
*     python manage.py runserver 

Now visit:

* Web app: http://127.0.0.1:8000

* API Docs: http://127.0.0.1:8000/api/docs

* Admin Panel: http://127.0.0.1:8000/admin
<br />


🔑 Authentication

* Web app: Django default authentication (username + password)

* API: HTTP Basic Authentication

When using Swagger UI, click Authorize and enter your Django username + password.
<br />


📡 API Overview

| Endpoint          | Method | Description                  |  Auth   |
| :---:             | :---:  | :---:                        | :---:   |
| /api/vehicles     | GET    | List available vehicles      | Public  |
| /api/reservations | GET    | List all reservations        | Staff   |
| /api/availability | GET    | Check vehicle availability   | Public  |

More endpoints will be added as the project grows.
👉 See full interactive docs at /api/docs.
<br />


📦 Database Structure (High-Level)

* accounts.CustomUser – user model with roles (user, manager, admin)

* inventory.Vehicle – vehicle model with type, engine, seats, etc.

* inventory.Location – pickup/return locations

* inventory.ReservationGroup – groups multiple reservations under one booking

* inventory.VehicleReservation – single vehicle reservation linked to a group
<br />


📝 Development Notes

* Reservations are split into:

*  Ongoing: Pending, Reserved

*  Archived: Completed, Rejected, Canceled

* Group actions allow approving/rejecting an entire reservation group at once

* Managers cannot access Django Admin; they manage everything via UI

* Unlimited seats logic applies automatically to Golf MK2 🚙
<br />


🚀 Future Improvements

* ✅ Integration with real payment providers

* ✅ Better test coverage

* ✅ Extended API (CRUD for vehicles, reservations, locations)
