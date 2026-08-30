# BNTI Cloud Deployment Guide (Zero Cost)

This system is set up to run automatically on **GitHub Actions**.
It will:
1. Request the Python Intelligence Analyzer hourly, providing headroom for a two-hour publication target.
2. Update the `bnti_data.js` file with latest threat assessments.
3. Publish the updated Dashboard to GitHub Pages.

## Step 1: Create a GitHub Repository

1. Go to **[github.com/new](https://github.com/new)** and sign in.
2. Create a **New Repository**:
   - Name: `border-neighbor-threat-index`
   - Visibility: **Public** (Required for free GitHub Pages)
   - **Do not** initialize with README (you already have one)

## Step 2: Upload Files

### Option A: Using GitHub Desktop (Easiest)

1. Download **[GitHub Desktop](https://desktop.github.com/)**.
2. File â†’ Add Local Repository â†’ Select your `border-neighbor-threat-index` folder.
3. Click "**Publish Repository**" to push to GitHub.

### Option B: Using Command Line

Open a terminal in your folder and run:

```bash
git init
git add .
git commit -m "Initial Border Neighbor Threat Index deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/border-neighbor-threat-index.git
git push -u origin main
```
*(Replace `YOUR_USERNAME` with your GitHub username)*

## Step 3: Enable Automation

1. Go to your repository on GitHub.
2. Click **Settings** â†’ **Pages** (left sidebar).
3. Under **Build and deployment**:
   - **Source: GitHub Actions** (Important! Do not select "Deploy from branch")
4. Go to the **Actions** tab:
   - You should see "BNTI Intelligence Update" listed.
   - Click "Run workflow" to test it manually.
5. Add repository secrets under **Settings** -> **Secrets and variables** -> **Actions**:
   - `OPENROUTER_API_KEY`
   - `OPENROUTER_API_KEY_BACKUP`

## Step 4: View Your Live Dashboard

Once the workflow completes (~15 minutes first time):

ðŸŒ **Your dashboard will be live at:**
```
https://YOUR_USERNAME.github.io/border-neighbor-threat-index/
```

The system requests an hourly update through GitHub Actions. GitHub schedules are best-effort; the public header shows actual freshness and clearly marks delays.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Actions not running | Check Settings â†’ Actions â†’ Enable "Allow all actions" |
| Pages not deploying | Ensure Source is set to "GitHub Actions", not "Branch" |
| 404 after deploy | Wait 2-3 minutes; GitHub Pages can have propagation delay |

---

<p align="center">ðŸ›°ï¸ <strong>Continuous Intelligence Monitoring</strong></p>

