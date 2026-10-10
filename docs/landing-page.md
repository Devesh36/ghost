# Ghost Next.js frontend

The landing page lives in `site/` as a Next.js App Router application using
React and TypeScript. It presents Ghost's workflow, actual captured terminal
output, installation commands and FAQ. The page does not execute Ghost scanners or
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

- `app/page.tsx`: server-rendered product page and review workflow.
- `app/layout.tsx`: title, description, social metadata, favicon and theme color.
- `app/globals.css`: responsive terminal typography, layout and reduced-motion support.
- `scripts/generate-theme.mjs`: reads the Ghost palette from `config/theme.py`
  before dev, check and build; writes ignored `.generated/terminal-theme.css`.
  It also updates `content/terminal-palette.json`; commit that generated snapshot
  after CLI palette changes. Site-only deployments use the snapshot when the
  Python source is absent, so they do not need a Python runtime or special settings.
- `components/product-preview.tsx`: accessible tabs showing actual renderer
  output from `content/product-preview.json`, in wide and compact terminal layouts.
- `components/tabbed-content.tsx`: accessible React tabs and installation copying.
- `components/icons.tsx`: independently authored SVG UI icons.
- `public/assets/ghost-icon.svg`: the existing Ghost-owned mascot.

All product captures and the default install content are available before
hydration and without JavaScript. Interactive controls appear after hydration, support arrow keys,
Home and End, and keep ARIA selection in sync. Copy uses the clipboard on
HTTPS/localhost and selects the command for manual copying if access fails.
FAQ disclosures are native HTML and work without JavaScript.

## Keep the content accurate

Keep installer commands aligned with `install.sh`, `Formula/ghost.rb` and
`docs/getting-started.md`. Keep suspected static candidates separate from
configured local access checks and verified, supported Python repairs.
Captured results come from an executed disposable sample, not the visitor's
repository. They are not security guarantees. The Python recipe's verified
helper status is distinct from the optional AI proposal's tested status.

## Verification

Verified on 9 October 2026: clean `npm ci`, route/type generation, TypeScript
checking and the Next.js production build all pass. Chromium checks against
the production server pass at 320, 390, 768, 1024, 1440 and 1920 pixels wide,
including workflow tabs, keyboard focus, exact copied installation commands,
FAQ disclosures, defaults without JavaScript and clipboard-failure selection.
No browser runtime, hydration or asset errors were observed. Desktop and mobile
renders were inspected. Vercel deployment is prepared, not yet created.

On 10 October 2026, the product-page refresh passed TypeScript checking and the
production build. Chromium checks covered 13 widths from 320 to 1920 pixels:
both routes matched all nine actual CLI palette values, page layouts had no
horizontal overflow, product tabs kept a stable height and supported keyboard
navigation, all three install commands copied exactly, and clipboard failure
selected the command. The complete dated history and disclosures remained
accessible. All six 1920-pixel gallery captures loaded; product captures, gallery
views, phases and the default installation remained available without JavaScript.

## User documentation route

The landing page now links to `/docs` through shared navigation. The guide covers
installation on macOS/Linux, current-directory project selection, Python test
environments, scan/brief/findings, chat and requested fixes, precise repair
runner support, updating and common blocked states. It includes copyable commands
and a responsive contents menu that works without JavaScript.

The guide has a three-step quick start, grouped contents, and an active section
indicator. On mobile, the contents collapse into a native disclosure. The
terminal walkthrough uses six fresh captures: workspace, command help, brief,
findings, Python repair, and a local chat action. All use the Ghost default
palette, one font, a consistent frame, and the same capture width. Tabs support
keyboard navigation; without JavaScript, all six views remain available. Long
output scrolls within the capture, with full-resolution links. Older promotional
illustrations are no longer displayed in this gallery.

Regenerate captures from the repository root with the prepared Python environment:

```bash
TERM=xterm-256color PYTHONPATH=. GHOST_THEME=ghost GHOST_NO_ANIMATION=1 \
  .venv/bin/python scripts/capture_site_gallery.py
node site/scripts/render-gallery.mjs
```

The Python command needs a working OS sandbox, installed Bandit/Semgrep, and
the locked development dependencies. In this cloud container, launch it through
the installed Tini reaper and use the platform's command escalation for nested
Bubblewrap. The renderer uses separately installed Playwright and Chromium;
set `CHROMIUM_PATH` if Chromium is elsewhere. It writes fresh PNGs and their
dimensions to `site/content/terminal-gallery.json`. HTML and executable evidence
are ignored under `.ghost/site-gallery/`. Sample source is unchanged, the Python
proposal is not applied, and no model provider is contacted.

The Python capture script also refreshes `site/content/product-preview.json`
using Ghost's actual Rich renderers at 68 and 36 columns. These escaped,
inline-styled exports are trusted build content, never visitor input. The
landing page uses the compact export on small screens and keeps long output
inside a keyboard-accessible scroll region. `--workspace-only` updates the
workspace/help gallery captures without running scans or changing the product
exports. Regenerate the full set after changing renderer output or the palette.

## Dated development phases

The landing page's `#phases` section is linked from shared navigation and the
footer. It groups development into dated phases and includes each available
commit, its change summary, and a source link. Dates use Asia/Kolkata. Merge
commits remain in the record.

`site/scripts/generate-history.mjs` runs before dev, check, and build. It merges
Git history with `site/content/commit-history.json`, so new commits appear and
shallow or Git-free deployments preserve recorded history. Run
`npm run history:update` from `site` to refresh the tracked snapshot. Future
development conversations should add an accurate outcome to
`site/content/development-notes.json`; unavailable chats are not invented.
The repository's `AGENTS.md` records this maintenance rule.
