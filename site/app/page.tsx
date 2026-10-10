import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-navigation";
import { ArrowIcon } from "../components/icons";
import { DevelopmentPhases } from "../components/development-phases";
import { ProductPreview } from "../components/product-preview";
import { InstallGhost } from "../components/install-ghost";

const capabilities = [
  {
    command: "ghost find",
    title: "Review the code you’re working on.",
    description:
      "Run local Python checks and four focused JavaScript / TypeScript rules. Inspect findings alongside scope, file locations, and scanner evidence.",
    detail: "Offline static checks · Saved locally",
  },
  {
    command: "ghost solve <id> --tests …",
    title: "Test the change before it reaches your repo.",
    description:
      "Ghost tests a supported Python recipe or an optional AI proposal in a disposable Git worktree. Review the diff and test results before approving application.",
    detail: "Isolated experiments · Approval required",
  },
  {
    command: "ghost run / ghost debug",
    title: "Keep the context behind a failure.",
    description:
      "Record the commands you choose to run, watch edits when you ask, and investigate failures with their saved output and session history.",
    detail: "Explicit capture · Revisit the evidence",
  },
];

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="landing">
        <section className="product-hero wrap" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="status-dot" /> LOCAL DEVELOPMENT AGENT
            </p>
            <h1 id="hero-title">
              Security review.
              <br />
              In your terminal.
            </h1>
            <p className="hero-description">
              Ghost reviews your code, investigates failures, and tests proposed
              repairs in isolated worktrees. You decide what changes.
            </p>
            <div className="hero-actions">
              <a className="button" href="#install">
                Install Ghost <ArrowIcon />
              </a>
              <Link className="button button-outline" href="/docs">
                Read the docs
              </Link>
            </div>
            <p className="hero-platform">
              macOS &amp; Linux <span>/</span> Python 3.12+
            </p>
            <div className="hero-release">
              <span>v0.1.0</span> Early access · MIT open source
            </div>
          </div>
          <div className="hero-product">
            <ProductPreview />
          </div>
        </section>

        <div className="product-facts wrap" aria-label="Ghost product facts">
          <span>Python + JavaScript / TypeScript</span>
          <span>Local by default</span>
          <span>AI connection optional</span>
          <span>Source changes need approval</span>
        </div>

        <section
          id="workflow"
          className="workflow wrap section"
          aria-labelledby="workflow-title"
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">THE WORKFLOW</p>
              <h2 id="workflow-title">A review you can act on.</h2>
            </div>
            <p>
              Start with your repository. Keep the findings, evidence, and
              proposed change in the same workflow.
            </p>
          </div>
          <ol className="workflow-steps">
            <li>
              <span className="step-index">01 / SCAN</span>
              <h3>Know what was checked.</h3>
              <p>
                Inspect the source scope, run local checks, and see incomplete
                coverage with the findings.
              </p>
              <code>
                <span>$</span> ghost find
              </code>
            </li>
            <li>
              <span className="step-index">02 / INVESTIGATE</span>
              <h3>Read the evidence.</h3>
              <p>
                Open a finding, trace its inputs, or read a saved brief. A
                pattern match is a starting point.
              </p>
              <code>
                <span>$</span> ghost brief
              </code>
            </li>
            <li>
              <span className="step-index">03 / TEST &amp; APPROVE</span>
              <h3>Inspect a proposed repair.</h3>
              <p>
                For supported repairs, run your selected tests in isolation.
                Review the patch before applying it.
              </p>
              <code>
                <span>$</span> ghost solve &lt;id&gt; --tests …
              </code>
            </li>
          </ol>
        </section>

        <section
          id="capabilities"
          className="capabilities wrap section"
          aria-labelledby="capabilities-title"
        >
          <div className="capabilities-intro">
            <p className="eyebrow">YOUR LOCAL WORKSPACE</p>
            <h2 id="capabilities-title">
              From finding
              <br />
              to tested change.
            </h2>
            <p>
              Use commands directly or work with Ghost in the REPL. Connect your
              own AI provider when you want advice or a tested proposal.
            </p>
            <Link className="text-link" href="/docs#support">
              Supported workflows <ArrowIcon />
            </Link>
          </div>
          <div className="capability-list">
            {capabilities.map((item) => (
              <article key={item.command}>
                <code>{item.command}</code>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <span className="capability-detail">{item.detail}</span>
              </article>
            ))}
          </div>
        </section>

        <section className="ownership wrap" aria-labelledby="ownership-title">
          <div>
            <img src="/assets/ghost-icon.svg" width="60" height="60" alt="" />
            <h2 id="ownership-title">Your project stays yours.</h2>
          </div>
          <p>
            Default reviews run offline and save evidence in{" "}
            <code>.ghost/</code>. AI source sharing is opt-in. Ghost shows the
            proposed diff and asks before applying a change.
          </p>
          <a className="text-link" href="/docs#support">
            Read the boundaries <ArrowIcon />
          </a>
        </section>

        <InstallGhost />
        <DevelopmentPhases />

        <section className="faq wrap section" aria-labelledby="faq-title">
          <div>
            <p className="eyebrow">BEFORE YOU INSTALL</p>
            <h2 id="faq-title">A few practical details.</h2>
            <a
              className="text-link"
              href="https://github.com/Devesh36/ghost/issues"
            >
              Ask on GitHub <ArrowIcon />
            </a>
          </div>
          <div className="faq-list">
            <details>
              <summary>
                Do I need an AI subscription?<span aria-hidden="true">+</span>
              </summary>
              <p>
                No. Static reviews, saved findings, briefs, and the supported
                Python repair recipe work without a model or API key. AI
                assistance uses the provider you choose, including local Ollama.
              </p>
            </details>
            <details>
              <summary>
                What can Ghost repair today?<span aria-hidden="true">+</span>
              </summary>
              <p>
                The deterministic recipe covers a constrained Python
                eval-to-literal-parser pattern. Optional AI proposals support
                one Python or plain JavaScript file with explicitly selected
                tests. TypeScript, Jest, and Vitest repairs are unsupported. AI
                proposals are tested, not security-verified.
              </p>
            </details>
            <details>
              <summary>
                Does my code leave my machine?<span aria-hidden="true">+</span>
              </summary>
              <p>
                Default static scans run locally. Optional AI reviews and
                proposals share the selected source or context with your
                configured provider, with your consent. Reviews and command
                history are stored in your project’s .ghost directory.
              </p>
            </details>
            <details>
              <summary>
                What does a clean scan mean?<span aria-hidden="true">+</span>
              </summary>
              <p>
                The scoped checks completed without reported findings. Ghost has
                bounded coverage; a clean scan does not certify your application
                secure. Use it alongside project tests and human review.
              </p>
            </details>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
