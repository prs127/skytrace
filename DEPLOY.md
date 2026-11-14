# Deploying Skytrace (Google Cloud Run + GitHub)

Everything happens in **Google Cloud Shell**, a free terminal in your browser. Nothing to install.
Total time is about 30 minutes; the first build alone takes 5–10 minutes.

## Step 1. Claim the Google Cloud offer
1. Space Apps Global Offers → **Google Cloud → Claim Offer** → **Get started for free**.
2. Sign in with your Google account. Accept the free trial: $300 credit for 90 days. The card is only for identity
   checks; there is no auto-charge after the trial unless you upgrade.

## Step 2. Create the project and a safety budget
1. Open <https://console.cloud.google.com>. In the project picker (top left), choose **New project**, name it
   `skytrace`, and click **Create**. Write down the **Project ID** shown (it can differ from the name, e.g. `skytrace-471203`).
2. Menu → **Billing**: check that the project uses the free-trial billing account.
3. Billing → **Budgets & alerts** → **Create budget**: $10, with email alerts at 50/90/100%. This only alerts you; it
   does not stop anything.

## Step 3. Make a GitHub token so Cloud Shell can push to your repo
GitHub → your picture → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
- Name: `skytrace-cloudshell`; Expiration: 7 days
- Repository access: **Only select repositories** → `prs127/skytrace`
- Permissions → Repository: **Contents: Read and write** and **Workflows: Read and write** (needed for the Pages workflow file)
- Click **Generate**, copy the token (starts `github_pat_`). Keep it private: never paste it in a chat.

## Step 4. Open Cloud Shell and put the code in your GitHub repo
1. In the Cloud Console click **Activate Cloud Shell** (the `>_` icon, top right).
2. Cloud Shell menu ⋮ → **Upload** → choose `skytrace-deploy.zip`.
3. Paste these lines (use your name and email for git):

```bash
unzip -q skytrace-deploy.zip && cd skytrace
git init -b main
git config user.name "Pardis"
git config user.email "YOUR-GITHUB-EMAIL"
git add -A && git commit -q -m "Skytrace: SPHEREx motion and spectrum viewer"
git remote add origin https://github.com/prs127/skytrace.git
git push -u origin main
```
When asked: **Username** = `prs127`, **Password** = paste the token (nothing shows while pasting; that is normal).
Refresh <https://github.com/prs127/skytrace>: the files should be there.

## Step 5. Deploy the live site to Cloud Run
Still in the `skytrace` folder in Cloud Shell:

```bash
gcloud config set project YOUR-PROJECT-ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud run deploy skytrace \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi --cpu 2 \
  --max-instances 1 \
  --no-cpu-throttling \
  --timeout 300
```
- If asked to create an Artifact Registry repository, answer **Y**.
- If asked "Allow unauthenticated invocations?", answer **y**.
- At the end it prints `Service URL: https://skytrace-….run.app`. **That is your live URL.**

Open it: the green badge at top right should say **Live IRSA archive**. Test: type `10h03m07.63s +03d21m00.8s` and press Go;
after about 1–2 minutes a new field appears.

Why the flags: one instance, because search jobs live in the server's memory; CPU always on, so downloads continue between
progress checks; 2 GB memory for the solid-angle maps and fields. With no minimum instances it scales to zero when idle,
so it costs almost nothing; the first visit after a quiet period takes 10–20 s to wake.

## Step 6. Put the live URL into the site and publish the backup on GitHub Pages
In Cloud Shell, replace the URL below with yours, then run:

```bash
sed -i "s#window.SKYTRACE_LIVE_URL = '';#window.SKYTRACE_LIVE_URL = 'https://YOUR-SERVICE-URL.run.app/';#" frontend/config.js
git commit -qam "Set live URL" && git push
gcloud run deploy skytrace --source . --region us-central1
```
(The second deploy reuses all the settings from Step 5.)

Then on GitHub: repo **Settings → Pages → Build and deployment → Source: GitHub Actions**. The workflow publishes
`frontend/` at `https://prs127.github.io/skytrace/` within a few minutes (watch the **Actions** tab). This backup shows
the six pre-built fields and sends any other position to the live site.

## Step 7. Test like a judge
Open each link in a **private/incognito** window, signed out:
- Live site (Cloud Run URL)
- Backup: `https://prs127.github.io/skytrace/`
- Repo: `https://github.com/prs127/skytrace`

## Updating later
After any change: `git commit -am "message" && git push` (updates GitHub and the Pages backup), then
`gcloud run deploy skytrace --source . --region us-central1` (updates the live site).

## Add the logo
Save it as `frontend/assets/logo.png` (square or wide PNG, about 256 px tall is plenty), then in `frontend/config.js` set
`window.SKYTRACE_LOGO = 'assets/logo.png';`. It appears in the top bar and as the browser-tab icon. Commit, push, redeploy.

## Run locally
```bash
pip install -r requirements.txt
cd backend && uvicorn server:app --port 8080     # open http://localhost:8080
```
