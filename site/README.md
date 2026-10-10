# Ghost website

Next.js App Router frontend for Ghost's landing page. Use Node.js 24.

```bash
npm ci
npm run dev
```

Open http://localhost:3000. For production verification:

```bash
npm run check
npm run build
npm start
```

Deploy on Vercel by importing `Devesh36/ghost`, setting **Root Directory** to
**`site`**, and selecting the **Next.js** preset. No environment variables or
API keys are required. Use `npm ci` and `npm run build`; keep the preset's
default output directory. Full instructions: [landing page guide](../docs/landing-page.md).

## Documentation

`/docs` is the in-site user guide. The landing page and shared header/footer link
to it. It covers system installation, using different Git projects, explicit
Python test environments, reviews, chat/fix consent, runner support, updates,
uninstalling, and troubleshooting. Commands render before hydration; copy buttons
appear with JavaScript and fall back to selecting text if clipboard access fails.
The mobile contents menu and help disclosures use native HTML.

The gallery uses six freshly executed sample views with one Ghost palette,
font, terminal frame, and capture width. Keyboard-accessible tabs keep the guide
compact; all views are available without JavaScript. Images have alt text,
dimensions, lazy loading, and full-resolution links. See the
[landing page guide](../docs/landing-page.md) to regenerate them.

## Development phases

The shared navigation links to the landing page's `#phases` timeline. Every
available commit is recorded by date (Asia/Kolkata), with a change summary and
GitHub link. Dev, check, and build refresh generated history automatically.
Run `npm run history:update` to refresh the tracked snapshot, which preserves
older entries in shallow or Git-free deployments. Add conversation outcomes to
`content/development-notes.json`; the repository's `AGENTS.md` records this
maintenance rule. Private chat transcripts are not published.
