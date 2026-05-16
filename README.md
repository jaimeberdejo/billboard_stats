# Billboard Stats

A web app for exploring Billboard chart history — browse the Hot 100 and Billboard 200, search any artist or song, and dig into historical records going back to 1958.

## What does it do?

Billboard Stats is a free, public music chart explorer. You don't need an account or login — just open the site and start digging through decades of chart data.

### Browse the charts

The home page shows the latest Billboard Hot 100 (singles) and Billboard 200 (albums) charts. You can switch between them and navigate backwards to any past week. Each entry shows the current position, last week's position, how many weeks it's been on the chart, and its peak position.

### Search

The search page lets you type any artist name, song title, or album name. Results are grouped by type (songs, albums, artists) in separate tabs, so you can quickly find what you're looking for even if you only remember part of the name.

### Records & leaderboards

The records page surfaces historical achievements: which songs spent the most weeks at #1, which artists charted the most songs, the longest consecutive chart runs, and more. There's also a custom query builder where you can filter and sort the data however you like.

### Detail pages

Click any song, album, or artist to see their full profile:

- **Song pages** — peak position, total weeks on chart, a visual chart run, and the complete week-by-week history table.
- **Album pages** — same layout as songs, but for Billboard 200 data.
- **Artist pages** — career stats, every Hot 100 song, and every Billboard 200 album that artist has had.

### Data status

A behind-the-scenes page at `/status` that shows when the data was last updated and how many records are in the database. Useful for confirming the data is fresh.

### How the data gets updated

The website itself is read-only. A separate Python process (the ETL) runs weekly, fetches the latest Billboard charts, and loads them into the database. The website then picks up the new data automatically. This means the site is always fast — it just reads from the database, it never does live scraping on page load.

---

## How to set it up on your machine

Follow these steps in order. Each one builds on the previous. If you run into an error, check the **Troubleshooting** section at the bottom.

---

### Prerequisites — what you need to install first

Before doing anything else, make sure the following are installed on your computer. Click the links to download them.

#### 1. Node.js (required)

Node.js is the runtime that powers the web app.

- Download: [nodejs.org](https://nodejs.org) — pick the **LTS** version (the one labeled "Recommended For Most Users")
- After installing, open a terminal and confirm it worked:

```bash
node --version
```

You should see something like `v20.x.x` or higher. If you see an error, restart your terminal and try again.

#### 2. Git (required)

Git lets you download the code from GitHub.

- **Mac:** Git is usually pre-installed. Check by running `git --version` in the terminal.
- **Windows:** Download from [git-scm.com](https://git-scm.com)
- **Linux:** Run `sudo apt install git` (Ubuntu/Debian) or `sudo dnf install git` (Fedora)

#### 3. Python 3.11 or newer (only needed for data loading)

Python is used to fetch Billboard chart data and load it into the database. You can skip this if someone else has already loaded the data.

- Download: [python.org](https://python.org) — pick version 3.11 or newer
- After installing, confirm it worked:

```bash
python --version
```

You should see `Python 3.11.x` or higher.

> **Mac note:** If `python` doesn't work, try `python3`. On newer Macs you may also need to install Python through [Homebrew](https://brew.sh): `brew install python`.

#### 4. A Neon PostgreSQL database (required)

The app stores all chart data in a PostgreSQL database hosted on [Neon](https://neon.tech). Neon has a free tier that is more than enough for this project.

1. Go to [neon.tech](https://neon.tech) and create a free account.
2. Click **"New Project"** and give it any name (e.g. `billboard`).
3. Once created, you'll land on the project dashboard. Keep this tab open — you'll need the connection strings in Step 3 below.

---

### Step 1 — Download the code

Open a terminal and run:

```bash
git clone https://github.com/jaimeberdejo/billboard_stats.git
cd billboard_stats
```

This creates a folder called `billboard_stats` on your computer with all the source code inside. Every command from here on should be run from inside that folder.

> **No Git?** You can also click the green "Code" button on GitHub and choose "Download ZIP", then unzip it.

---

### Step 2 — Install JavaScript dependencies

Inside the project folder, run:

```bash
npm install
```

This reads the `package.json` file and downloads all the JavaScript packages the app needs into a `node_modules` folder. It may take 30–60 seconds.

You should see output ending with something like:

```
added 312 packages in 45s
```

If you see errors instead, check that Node.js is installed correctly (Step 1 of Prerequisites).

---

### Step 3 — Create your configuration file

The app needs a file that tells it how to connect to your database. This file is called `.env.local` and lives in the root of the project folder.

#### 3a. Copy the template

```bash
cp .env.example .env.local
```

This creates `.env.local` from the provided template. Open it in any text editor (Notepad, TextEdit, VS Code, etc.).

It will look like this:

```
DATABASE_URL=postgresql://user:password@ep-pooler-name-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require

PGHOST=ep-<id>.us-east-1.aws.neon.tech
PGPORT=5432
PGDATABASE=neondb
PGUSER=<neon-user>
PGPASSWORD=<neon-password>
PGSSLMODE=require
```

You need to replace the placeholders with real values from Neon.

#### 3b. Get your Neon connection strings

1. Go to your [Neon dashboard](https://console.neon.tech) and open your project.
2. Click **"Connection Details"** in the left sidebar (or it may appear on the main page).
3. You'll see a dropdown that says **"Connection type"** — you need two different strings.

**For `DATABASE_URL` (the web app):**
- In the dropdown, select **"Pooled connection"**
- Copy the full connection string. It will look like:
  `postgresql://jaime:abc123@ep-cool-name-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require`
- Paste it as the value for `DATABASE_URL` in `.env.local`

**For the `PG*` variables (the Python ETL):**
- In the dropdown, select **"Direct connection"** (sometimes called "Unpooled")
- The connection string will look like:
  `postgresql://jaime:abc123@ep-cool-name.us-east-2.aws.neon.tech/neondb?sslmode=require`
- Break it apart and fill in each variable:

| Variable | Where it comes from |
|---|---|
| `PGHOST` | The hostname: `ep-cool-name.us-east-2.aws.neon.tech` |
| `PGPORT` | Always `5432` |
| `PGDATABASE` | The database name, usually `neondb` |
| `PGUSER` | Your Neon username (e.g. `jaime`) |
| `PGPASSWORD` | Your Neon password |
| `PGSSLMODE` | Always `require` |

> **Important:** Never share or commit your `.env.local` file. It contains your database password. The `.gitignore` already excludes it, so it won't accidentally get uploaded to GitHub.

---

### Step 4 — Start the web app

```bash
npm run dev
```

You'll see output like:

```
▲ Next.js 16.x.x
- Local:        http://localhost:3000
- Ready in 1234ms
```

Open your browser and go to **http://localhost:3000**

You should see the Billboard Stats app. If your database is empty, the pages will load but show no chart data — that's expected. Follow Step 5 to load data.

To stop the app, press `Ctrl + C` in the terminal.

---

### Step 5 — Load chart data into the database (Python ETL)

If you're starting with an empty database, you need to run the ETL (Extract, Transform, Load) process to fetch Billboard chart data and store it. This step uses Python.

#### 5a. Set up a Python virtual environment

A virtual environment keeps the Python packages for this project separate from the rest of your system.

```bash
python -m venv .venv
```

Then activate it:

- **Mac / Linux:**
  ```bash
  source .venv/bin/activate
  ```

- **Windows (Command Prompt):**
  ```bash
  .venv\Scripts\activate.bat
  ```

- **Windows (PowerShell):**
  ```bash
  .venv\Scripts\Activate.ps1
  ```

Your terminal prompt should now show `(.venv)` at the start, which means the virtual environment is active.

#### 5b. Install Python packages

```bash
pip install -r requirements.txt
```

This installs all the Python dependencies. It may take a minute or two.

#### 5c. Set up the ETL credentials file

The Python ETL reads its database credentials from a separate file: `billboard_stats/.env` (note: this is different from `.env.local`).

```bash
cp .env.example billboard_stats/.env
```

Open `billboard_stats/.env` and fill in the same `PG*` values you used in Step 3b (the direct/unpooled connection string values). The `DATABASE_URL` line is not needed here — you can delete it or leave it blank.

#### 5d. Run the ETL

```bash
python -m billboard_stats.etl.updater
```

This will:
1. Check which chart weeks are missing from your database
2. Download the missing chart data from Billboard
3. Load all new rows into PostgreSQL
4. Rebuild aggregate statistics (career totals, records, etc.)

The first run can take **5–15 minutes** depending on how much historical data it downloads. Subsequent runs are fast because they only fetch new weeks.

Once it finishes, refresh the app at http://localhost:3000 and you should see chart data.

#### 5e. Keep data fresh (optional)

To update the database with the latest charts in the future, just run the same command again:

```bash
python -m billboard_stats.etl.updater --update
```

Or use the included shell script:

```bash
chmod +x scripts/run_weekly_etl.sh
./scripts/run_weekly_etl.sh --update
```

---

### Step 6 — Verify everything is working

Open your browser and check each page:

| Page | URL | What to look for |
|---|---|---|
| Home / Charts | http://localhost:3000 | Hot 100 and Billboard 200 chart entries |
| Search | http://localhost:3000/search | Type an artist name, results appear |
| Records | http://localhost:3000/records | Leaderboard tables with data |
| Status | http://localhost:3000/status | Shows row counts and latest chart dates |

If all four pages show data, your setup is complete.

---

## Troubleshooting

**The app loads but all pages are empty**
Your database is empty. Follow Step 5 to run the Python ETL and load chart data.

**`Error: DATABASE_URL is not defined` or similar**
Your `.env.local` file is missing or the variable is not set. Make sure the file exists in the project root (not inside a subfolder) and that `DATABASE_URL` has a real value, not the placeholder text from the template.

**`connection refused` or `could not connect to server`**
The connection string is wrong. Go back to the Neon dashboard and re-copy the pooled connection string. Watch out for extra spaces or line breaks when pasting.

**`npm: command not found`**
Node.js is not installed. Download it from [nodejs.org](https://nodejs.org) (LTS version), install it, then open a new terminal window and try again.

**`python: command not found`**
Python is not installed. Download it from [python.org](https://python.org). On Mac, also try `python3` instead of `python`.

**`ModuleNotFoundError` when running the ETL**
You forgot to activate the virtual environment. Run `source .venv/bin/activate` (Mac/Linux) or `.venv\Scripts\activate` (Windows) before running the ETL command.

**`Missing required ETL environment variable: PGHOST`** (or similar)
The `billboard_stats/.env` file is missing or incomplete. Follow Step 5c and make sure all `PG*` variables have real values.

**Port 3000 is already in use**
Another app is running on port 3000. Either stop that app, or run the dev server on a different port: `npm run dev -- -p 3001`, then open http://localhost:3001.

---

## Project structure

```
billboard_stats/
├── src/                    # Next.js web app
│   ├── app/                # Pages and API routes
│   │   ├── page.tsx        # Home / charts
│   │   ├── search/         # Search page
│   │   ├── records/        # Records & leaderboards
│   │   ├── status/         # Data status
│   │   ├── song/[id]/      # Song detail
│   │   ├── album/[id]/     # Album detail
│   │   ├── artist/[id]/    # Artist detail
│   │   └── api/            # JSON API endpoints
│   └── lib/                # Database query helpers
├── billboard_stats/        # Python ETL package
│   ├── etl/                # Chart fetching and loading logic
│   ├── db/                 # Database connection and schema
│   └── services/           # Query layer (used by the legacy Streamlit app)
├── scripts/                # Shell helpers for running the ETL
├── .env.example            # Template for your .env.local
└── requirements.txt        # Python dependencies
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Web framework | Next.js 16 + React 19 |
| Language | TypeScript |
| Styling | Tailwind CSS 4 |
| Database | PostgreSQL (hosted on Neon) |
| Database client | @neondatabase/serverless |
| Data pipeline | Python 3.11+ with `billboard.py` |
| Hosting | Vercel |
