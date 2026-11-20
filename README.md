# Bookstall World

Bookstall World is a Flask + SQLAlchemy bookstore application with customer shopping flows, inventory management, order history, and a small order-based recommendation/analytics engine.

## Features

- Customer registration and login
- Product search and category filtering
- Shopping cart, stock-aware checkout, and order history
- Admin product management and order views
- Sales analytics, frequently bought-together bundles, and basic recommendations
- PostgreSQL support for deployment and SQLite for local development

## Stack

Python, Flask, Flask-SQLAlchemy, SQLAlchemy, PostgreSQL/SQLite, Jinja templates, and Werkzeug password hashing.

## Run locally

Use Python 3.10+.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Configure a private session secret and a strong initial administrator password (at least 12 characters).

Windows PowerShell:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-secret"
$env:INITIAL_ADMIN_PASSWORD = "replace-with-a-strong-password"
python app.py
```

macOS / Linux:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export INITIAL_ADMIN_PASSWORD="replace-with-a-strong-password"
python app.py
```

Open http://127.0.0.1:5000. For local development, the app uses a SQLite database configured by Flask-SQLAlchemy. The first run creates the tables and an administrator account named `admin`; the password is the value of `INITIAL_ADMIN_PASSWORD`.

## Deploying to Vercel with PostgreSQL

1. Create a PostgreSQL database and connect it to the Vercel project.
2. Configure `POSTGRES_URL_NON_POOLING` (preferred) or `POSTGRES_URL`.
3. Set `SECRET_KEY` to a long, random, private value.
4. Set `SETUP_TOKEN` to a separate random token.
5. Set `INITIAL_ADMIN_PASSWORD` to a strong password of at least 12 characters.
6. Set `SESSION_COOKIE_SECURE=true` when serving over HTTPS.
7. Deploy, then visit `/setup?token=YOUR_SETUP_TOKEN` once to create the database tables and initial administrator.

The setup endpoint does not return database exception details or default credentials. Check deployment logs for setup errors. Keep the setup token and initial password private; rotate/remove the setup token after initialization.

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing secret; required for stable deployed sessions |
| `INITIAL_ADMIN_PASSWORD` | Password used when creating the first `admin` account; minimum 12 characters |
| `SETUP_TOKEN` | Protects the one-time deployment setup endpoint |
| `POSTGRES_URL_NON_POOLING` | Preferred direct PostgreSQL connection URL |
| `POSTGRES_URL` | PostgreSQL fallback connection URL |
| `SESSION_COOKIE_SECURE` | Set to `true` for HTTPS deployments |
| `FLASK_DEBUG` | Set to `true` only for local debugging |

## Project structure

```text
Bookstall-World/
├── app.py
├── extensions.py
├── models.py
├── utils.py
├── requirements.txt
├── vercel.json
├── others/
├── static/
└── templates/
```

## Current limitations and security notes

- The recommendation engine is a lightweight heuristic using order co-occurrence, purchase history, category, and popularity signals; it is not a trained machine-learning recommender.
- This is a portfolio/demo application, not a production commerce platform.
- Add CSRF protection to all state-changing forms before public deployment.
- Use database migrations for schema changes and review transaction/locking behavior for concurrent checkout.
- Configure database backups, HTTPS, monitoring, and rate limits before handling real users or payments.
- Payment processing is not integrated; placing an order is a demonstration checkout flow.

## License

No license file is currently included. Contact the repository owner before reusing or redistributing this project.
