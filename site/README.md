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

The terminal gallery serves the four existing sample captures and their framed
versions, plus the saved brief SVG, from `public/assets/screenshots/`, plus separately labeled chat/fix
illustrations. Images have alt text, dimensions, lazy loading, and full-resolution
links. Preserve the distinction between executed samples and generated artwork.
