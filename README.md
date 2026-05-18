# 📚 Bookstall World — Vercel Deployment (100% Vercel, nothing else)

Everything — hosting + database — lives inside your Vercel account.

---

## Step 1 — Push code to GitHub

```bash
git init
git add .
git commit -m "bookstall world"
# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/bookstall-world.git
git push -u origin main
```

---

## Step 2 — Create project on Vercel

1. Go to **https://vercel.com** → sign up free with GitHub
2. Click **Add New → Project**
3. Import your `bookstall-world` repo → click **Deploy**
   - Build settings: leave everything as default
   - Don't add env vars yet — do that in Step 4

---

## Step 3 — Add a free Postgres database (inside Vercel)

1. In your Vercel project → click the **Storage** tab
2. Click **Create Database** → choose **Postgres** → click **Continue**
3. Keep default settings → click **Create**
4. Vercel creates the DB and **automatically connects it** to your project ✅
   - It injects `POSTGRES_URL` into your project's env vars automatically

---

## Step 4 — Add your 2 env vars

Go to your Vercel project → **Settings → Environment Variables** and add:

| Name | Value |
|---|---|
| `SECRET_KEY` | Any long random string e.g. `xK9mP2qLnR5vW3jA7bZ4cF` |
| `SETUP_TOKEN` | Any secret word e.g. `bookstall2026` |

Click **Save**, then go to **Deployments → Redeploy** (so the new vars take effect).

---

## Step 5 — Initialise the database (one time only)

Visit this URL in your browser (replace with your actual values):

```
https://YOUR-APP.vercel.app/setup?token=bookstall2026
```

You'll see:
```
✅ Database ready! Login at /login  (admin / 123)
```

This creates all tables and adds the default accounts.

---

## Step 6 — You're live! 🎉

Visit your app URL. Login credentials:
- **Admin:** `admin` / `123` ← change this immediately!
- **Customer:** `alice` / `alice123`

Every time you push to GitHub, Vercel auto-redeploys.

---

## Project structure

```
bookstall-world/
├── app.py              ← Flask app (Vercel entry point)
├── models.py           ← Database models (PostgreSQL-compatible)
├── extensions.py       ← db instance
├── utils.py            ← decorators + recommendation engine
├── vercel.json         ← Vercel routing config
├── requirements.txt    ← Python dependencies (uses psycopg2 for Postgres)
├── .env.example        ← Template — copy to .env for local dev
├── .gitignore
├── static/css/style.css
└── templates/*.html
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| App loads but shows error | Visit `/setup?token=YOUR_TOKEN` first |
| "POSTGRES_URL is not set" | Make sure the Postgres store is linked to the project in the Storage tab |
| Env vars not working | After adding vars → go to Deployments → Redeploy |
| Want to reset the DB | In Vercel Storage → your DB → Query tab, run `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` then visit `/setup?token=...` again |
