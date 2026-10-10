# Ghost Next.js frontend

The landing page lives in `site/` as a Next.js App Router application using
React and TypeScript. Its design, mascot, illustrative workflow, installation
commands and FAQ are preserved. The page does not execute Ghost scanners or
upload visitor code. There are no API keys, backend services, remote fonts or
analytics to configure.

## Run locally

Use Node.js 24 (also recorded in `site/.nvmrc` and `package.json`):

```bash
cd site
npm ci
npm run dev
```

Open <http://localhost:3000>. To verify and preview production:

```bash
npm run check
npm run build
npm start
```

`check` generates Next route types and checks TypeScript. `package-lock.json`
pins the dependency tree; commit its updates with dependency changes. Build
outputs, dependency folders and Vercel project settings are ignored by Git.

## Deploy on Vercel

1. In Vercel, choose **Add New → Project** and import `Devesh36/ghost` from GitHub.
2. Set **Root Directory** to **`site`**. This is required: the repository root
   contains Ghost's Python CLI, while the frontend package lives in `site/`.
3. Choose **Next.js** as the framework preset and **Node.js 24.x** as the runtime.
4. Use **`npm ci`** for installation and **`npm run build`** for the build.
   Leave the output directory at the Next.js preset default; do not set it to `site` or `out`.
5. Leave environment variables empty and select **Deploy**.

Vercel supplies the deployment URL. Review that URL before attaching a custom
domain. A Git-connected Vercel project can create preview deployments for pull
requests and production deployments from `main`. The repository does not
contain Vercel credentials or create a Vercel project automatically.

The old static GitHub Pages publishing workflow has been replaced with
**Frontend checks**, which installs locked dependencies, checks types and builds
Next.js on frontend pull requests and pushes. These checks do not publish a site.
The separately added legacy Jekyll workflow remains available for manual use;
its automatic main-push trigger is disabled because it does not build Next.js.

## Code structure

- `app/page.tsx`: server-rendered landing page content and illustrative panels.
- `app/layout.tsx`: title, description, social metadata, favicon and theme color.
- `app/globals.css`: the responsive dark/mint design and reduced-motion support.
- `components/tabbed-content.tsx`: accessible React tabs and installation copying.
- `components/icons.tsx`: independently authored SVG UI icons.
- `public/assets/ghost-icon.svg`: the existing Ghost-owned mascot.

The default review and install content is available before hydration and without
JavaScript. Interactive controls appear after hydration, support arrow keys,
Home and End, and keep ARIA selection in sync. Copy uses the clipboard on
HTTPS/localhost and selects the command for manual copying if access fails.
FAQ disclosures are native HTML and work without JavaScript.

## Keep the content accurate

Keep installer commands aligned with `install.sh`, `Formula/ghost.rb` and
`docs/getting-started.md`. Keep suspected static candidates separate from
configured local access checks and verified, supported Python repairs.
Illustrative panels are examples, not live scan results or security guarantees.

## Verification

Verified on 9 October 2026: clean `npm ci`, route/type generation, TypeScript
checking and the Next.js production build all pass. Chromium checks against
the production server pass at 320, 390, 768, 1024, 1440 and 1920 pixels wide,
including workflow tabs, keyboard focus, exact copied installation commands,
FAQ disclosures, defaults without JavaScript and clipboard-failure selection.
No browser runtime, hydration or asset errors were observed. Desktop and mobile
renders were inspected. Vercel deployment is prepared, not yet created.

## User documentation route

The landing page now links to `/docs` through shared navigation. The guide covers
installation on macOS/Linux, current-directory project selection, Python test
environments, scan/brief/findings, chat and requested fixes, precise repair
runner support, updating and common blocked states. It includes copyable commands
and a responsive contents menu that works without JavaScript.

The gallery contains four executed sample terminal captures with their original
presentation versions, the separate saved brief capture, and two user-requested chat/fix illustrations. Illustrations
are labeled; none of the screenshots claims universal application security.
Full-resolution links are available. Assets are served locally from the Next.js
public directory without an external image host.
