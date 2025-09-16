Vercel webhook + catalog for Telegram -> GitHub storage


Steps:

1) Create a GitHub repo (owner/repo) and create an empty catalog.json with [] on the default branch (main).

2) Create a GitHub Personal Access Token (repo scope) and set it as GITHUB_TOKEN in Vercel env.

3) Create a Telegram Bot with BotFather and copy the token; set BOT_TOKEN in Vercel env.
Add the bot as admin to your channel so it receives posts.

4) Set GITHUB_REPO env in Vercel like owner/repo and optionally GITHUB_PATH (default catalog.json).
Deploy the vercel_api folder to Vercel (connect GitHub repo or use Vercel CLI).
Example: push this vercel_api folder to a GitHub repo and import it in Vercel.

5) After deployment, set Telegram webhook:

   https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<your-vercel-app>.vercel.app/api/webhook

6) Test: post a message with a magnet link in the channel; the webhook will add it to the GitHub catalog.json.
7) Your Kodi addon should be configured to point to https://<your-vercel-app>.vercel.app/api/catalog as its Catalog URL.

Security: keep tokens secret. This example stores data in your GitHub repo; ensure private repo if you prefer privacy.
