# Ghost landing page

The landing page lives in `site/`. It is plain HTML, CSS and JavaScript with no
build step, frontend dependency installation, analytics, remote fonts or CDN.
Its mascot is Ghost's existing independently authored SVG. Workflow panels
are explicitly illustrative examples; the page does not run scanners or
claim to show a live project review.

## Preview locally

From a Ghost checkout:

```bash
python -m http.server 4173 --directory site
```

Open <http://localhost:4173>. The install commands stay selectable when
JavaScript is disabled. With JavaScript enabled, installation and workflow
tabs support arrow keys, Home and End. Copy buttons use the clipboard on
HTTPS/localhost; if unavailable, they select the command for manual copying.
FAQ disclosures work without JavaScript. The page respects reduced-motion
preferences and uses relative asset links so it works under `/ghost/`.

## Publish with GitHub Pages

1. In the repository's **Settings → Pages**, choose **GitHub Actions** as the source.
2. In **Actions → Publish landing page**, select **Run workflow** on `main`.
3. Wait for both jobs to pass. Open the deployment URL shown by the workflow.

The expected project URL is <https://devesh36.github.io/ghost/> when published
under the default GitHub Pages domain. A custom domain or existing Pages
configuration may change it. Repository Pages settings need owner/admin
access; adding this workflow does not enable Pages or publish the site by
itself. Publishing is manual, including updates. The workflow uploads only
`site/`, and uses pinned actions with write permissions confined to deployment.

For another static host, use `site/` as the publish directory and leave the
build command empty. Use HTTPS for clipboard support. No secrets are needed.

## Maintain the content

Keep the installer commands aligned with `install.sh`, `Formula/ghost.rb`
and `docs/getting-started.md`. Keep evidence descriptions aligned with the
CLI: suspected static candidates, configured local access checks, isolated
supported Python repairs, and approval before application. Never turn a
completed scoped scan into an application security guarantee.

## Verification

Verified locally in Chromium at 320, 390, 768, 1024, 1440 and 1920 pixels wide:
no page overflow, workflow tab changes, keyboard navigation, exact copied
installation commands, FAQ toggles, readable defaults without JavaScript,
and manual selection when clipboard access fails. Desktop and mobile renders
were inspected. `node --check site/app.js` and static asset/link checks pass.
This does not establish Safari/Firefox or hosted deployment compatibility;
check the published URL after a successful Pages run.
