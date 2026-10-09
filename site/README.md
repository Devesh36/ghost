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
