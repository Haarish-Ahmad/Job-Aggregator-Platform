# Server setup

Makes a Linux laptop (Ubuntu or Debian, 64-bit, ideally 8 GB of RAM or more) the server for this project.

## First-time steps, in order

### 1. Commit your work and push it

```bash
git add .gitattributes .github README.md docker-compose.prod.yml server-setup
git commit -m "Add server setup and automatic deploy"
git push
```

### 2. Prepare the merge into main (first time only)

`main` went through a revert, so a normal merge there loses files. This merge keeps your branch's content exactly:

```bash
git switch -c merge-to-main
git merge -s ours origin/main -m "Merge main, keeping this branch's content"
git push -u origin merge-to-main
```

### 3. Merge it on GitHub

Open a pull request from `merge-to-main` into `main`. Wait for CI to pass, then merge with **Create a merge commit**, not squash.

### 4. Wait for Release to finish

Watch it in the Actions tab. It publishes the four images. The `deploy` job shows as skipped, which is correct for now.

### 5. Set up the laptop

Copy this folder to the laptop, then run it as your normal user:

```bash
cd server-setup
bash setup.sh
```

It installs Docker and git, keeps the laptop awake, creates `~/job-aggregator/deploy.env` with random passwords, and
connects the laptop to GitHub. It asks for your password and for a one-time token from a GitHub page it shows you.

### 6. Finish on github.com

- Settings, Actions, Runners: your laptop must show as **Idle**.
- Settings, Secrets and variables, Actions, Variables: add `DEPLOY_ENABLED` = `true`.
- Settings, Actions, General: choose **Require approval for all external contributors**. Don't skip this: the
  repository is public, and a stranger's pull request must never run on your laptop.

### 7. Start the site

In the Actions tab, open **Release**, then click **Run workflow** on `main`. The first run is slow because Firecrawl is
built on the laptop.

### 8. Open the site

The site is at `http://<laptop-address>/`, and Grafana at `/grafana/` (user `admin`, password in `deploy.env`).

## After that

Open a pull request and merge it into `main`. There is nothing else to do:

1. Release builds the images on GitHub and uploads them.
2. The laptop runs `deploy.sh`, which starts Firecrawl and the new version of the app.

Your data is kept between deploys. The laptop must be on and connected to the internet for a deploy to run.
