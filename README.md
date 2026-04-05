# Expense Manager

A full-stack expense tracking web application built with **Django** and **Django templates**. Users track shared expenses across discrete events, with balances that always sum to zero.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5 |
| Auth | Django session auth |
| Frontend | Django templates, HTML/CSS |
| Package manager (Python) | uv |
| Database | SQLite (dev) |

---

## Architecture Overview

Django handles both the backend logic and HTML rendering. Views process requests, apply business logic, and return rendered templates. There is no separate frontend build step or API layer — all pages are server-rendered.

---

## Data Model

### `User` (extends `AbstractUser`)
| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | PK |
| `username` | CharField | unique |
| `email` | EmailField | |
| `is_admin` | BooleanField | designates administrator role |

### `Event`
| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | PK |
| `name` | CharField | |
| `description` | TextField | optional |
| `created_by` | FK → User | |
| `created_at` | DateTimeField | auto |
| `members` | M2M → User (via `EventMembership`) | |

### `EventMembership`
Join table between `User` and `Event`. Stores each user's running balance within an event.

| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | PK |
| `user` | FK → User | |
| `event` | FK → Event | |
| `balance` | DecimalField(10,2) | running balance; sum across all members always = 0 |

### `Transaction`
| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | PK |
| `event` | FK → Event | |
| `description` | CharField | |
| `amount` | DecimalField(10,2) | total amount paid |
| `paid_by` | FK → User | the member who paid |
| `created_at` | DateTimeField | auto |

### `TransactionSplit`
Records how a transaction is divided among event members.

| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | PK |
| `transaction` | FK → Transaction | |
| `user` | FK → User | |
| `amount` | DecimalField(10,2) | this user's share (positive = owes) |

**Balance invariant:** when a transaction is saved, the payer's balance increases by the total amount and each member's balance decreases by their split amount. Because splits sum to the total, the net change across all members is always zero.

---

## Pages & URLs

| URL | View | Description |
|---|---|---|
| `/` | `dashboard` | List of user's events with balance summary |
| `/events/<id>/` | `event_detail` | Member balances and transaction list |
| `/events/<id>/add/` | `add_transaction` | Add transaction form (equal or manual split) |
| `/events/<id>/transactions/<tx_id>/delete/` | `delete_transaction_view` | Delete a transaction |
| `/admin/users/` | `manage_users` | Create/edit/delete users _(admin only)_ |
| `/admin/events/` | `manage_events` | Create events and assign members _(admin only)_ |

### Templates

```
templates/
├── base.html              Base layout with navigation
├── login.html             Login page
├── dashboard.html         Event list with per-event balances
├── event_detail.html      Member balances and transaction list
├── add_transaction.html   Add transaction (equal/manual split)
└── admin/
    ├── manage_users.html  User management (admin only)
    └── manage_events.html Event and member management (admin only)
```

---

## Running Locally

```bash
uv run manage.py migrate
uv run manage.py createsuperuser
uv run manage.py runserver
```

Visit `http://localhost:8000`.

---

## Deployment (Docker)

The app runs behind an nginx reverse proxy at `https://home.albachten.com/receipts`.

### 1. Set a secret key

Edit `docker-compose.yml` and replace `SECRET_KEY` with a long random string:

```bash
python -c "import secrets; print(secrets.token_hex(50))"
```

### 2. Build and start

```bash
docker compose up -d
```

On first start the container automatically runs migrations. The SQLite database is persisted in a named Docker volume (`db_data`).

### 3. Create an admin user

```bash
docker compose exec app uv run python manage.py createsuperuser
```

### 4. Nginx configuration

Add this block to your nginx config:

```nginx
location /receipts/ {
    proxy_pass http://localhost:8666/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The trailing slash on both `location` and `proxy_pass` strips the `/receipts` prefix before forwarding to the container. Django uses the `SCRIPT_NAME` env var to reconstruct correct URLs for links, redirects, and static files.

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Long random string |
| `DEBUG` | No | `False` in production |
| `ALLOWED_HOSTS` | Yes | Comma-separated hostnames |
| `SCRIPT_NAME` | Yes | URL prefix, e.g. `/receipts` |
| `CSRF_TRUSTED_ORIGINS` | Yes | Comma-separated origins, e.g. `https://home.albachten.com` |

---

## Environment Variables (`.env`, local dev only)

```
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```
