import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-navigation";
import { TabbedContent } from "../components/tabbed-content";
import { ArrowIcon, TurnIcon } from "../components/icons";
import { DevelopmentPhases } from "../components/development-phases";

export default function Home() {
  return (
    <>
      <SiteHeader />

      <main id="main" className="landing">
        <section className="hero wrap" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="status-dot" aria-hidden="true"></span> YOUR
              TERMINAL. ONE STEP AHEAD.
            </p>
            <h1 id="hero-title">
              Find what
              <br />
              you <span className="serif">missed.</span>
              <br />
              <span className="muted-heading">Before you ship.</span>
            </h1>
            <p className="hero-description">
              A local security review, right in your terminal. Find patterns in
              Python, JavaScript, and TypeScript. Follow the evidence. Test a
              supported repair before changing your code.
            </p>
            <div className="hero-actions">
              <a className="button" href="#install">
                Install Ghost{" "}
                <span aria-hidden="true">
                  <ArrowIcon />
                </span>
              </a>
              <Link className="text-link" href="/docs">
                Explore the docs{" "}
                <span aria-hidden="true">
                  <ArrowIcon />
                </span>
              </Link>
            </div>
            <div className="hero-meta">
              <span>macOS &amp; Linux</span>
              <span>No API key needed</span>
              <span>Open source</span>
            </div>
          </div>

          <div className="hero-product">
            <div className="product-note">
              <span className="status-dot" aria-hidden="true" />A REVIEW, FROM
              FINDING TO FIX
            </div>
            <div className="terminal">
              <div className="terminal-bar">
                <span className="window-dots" aria-hidden="true">
                  <i></i>
                  <i></i>
                  <i></i>
                </span>
                <span>~/projects/my-app</span>
                <span className="terminal-mark" aria-hidden="true">
                  ⌘
                </span>
              </div>
              <TabbedContent
                appearance="terminal"
                ariaLabel="Sample workflow"
                tabs={[
                  {
                    id: "find",
                    label: "01 / Find",
                    content: (
                      <>
                        <p className="prompt">
                          <span>$</span> ghost find
                        </p>
                        <p className="terminal-label">
                          GHOST / SECURITY REVIEW
                        </p>
                        <div className="scan-state">
                          <span
                            className="status-dot"
                            aria-hidden="true"
                          ></span>{" "}
                          Scoped checks completed
                        </div>
                        <div className="terminal-stats">
                          <div>
                            <strong>02</strong>
                            <span>source files</span>
                          </div>
                          <div>
                            <strong>02</strong>
                            <span>static candidates</span>
                          </div>
                        </div>
                        <div className="finding">
                          <span className="severity">MEDIUM</span>
                          <div>
                            <strong>Expression evaluation</strong>
                            <span>
                              parser.py:2 <b>· B307</b>
                            </span>
                          </div>
                          <span className="finding-arrow" aria-hidden="true">
                            <ArrowIcon />
                          </span>
                        </div>
                        <div className="finding">
                          <span className="severity">MEDIUM</span>
                          <div>
                            <strong>JavaScript evaluation</strong>
                            <span>
                              client.ts:1 <b>· GJS001</b>
                            </span>
                          </div>
                          <span className="finding-arrow" aria-hidden="true">
                            <ArrowIcon />
                          </span>
                        </div>
                        <p className="terminal-hint">
                          Static leads. Investigate applicability.
                        </p>
                      </>
                    ),
                  },
                  {
                    id: "review",
                    label: "02 / Review",
                    content: (
                      <>
                        <p className="prompt">
                          <span>$</span> ghost findings --id &lt;finding-id&gt;
                        </p>
                        <p className="terminal-label">GHOST / FINDING DETAIL</p>
                        <div className="detail-heading">
                          <span className="severity">MEDIUM</span>
                          <strong>Expression evaluation</strong>
                        </div>
                        <p className="detail-path">
                          parser.py:2 <span>· B307 · suspected</span>
                        </p>
                        <div className="terminal-detail">
                          <strong>Why it matters</strong>
                          <p>
                            Expression evaluation can execute code rather than
                            only parse data.
                          </p>
                        </div>
                        <div className="terminal-detail">
                          <strong>What to verify</strong>
                          <p>
                            Trace the input into eval. Check who controls it and
                            whether evaluation is intended.
                          </p>
                        </div>
                        <p className="terminal-hint">
                          Pattern-match confidence ≠ exploitability.
                        </p>
                      </>
                    ),
                  },
                  {
                    id: "repair",
                    label: "03 / Repair",
                    content: (
                      <>
                        <p className="prompt">
                          <span>$</span> ghost solve &lt;id&gt; --tests "python
                          -m unittest"
                        </p>
                        <p className="terminal-label">
                          GHOST / SUPPORTED PYTHON REPAIR
                        </p>
                        <div className="repair-line">
                          <span aria-hidden="true">✓</span>
                          <div>
                            <strong>Reproduce the behavior</strong>
                            <p>Check the selected literal-parser recipe.</p>
                          </div>
                        </div>
                        <div className="repair-line">
                          <span aria-hidden="true">✓</span>
                          <div>
                            <strong>Test an isolated change</strong>
                            <p>Run the probe and your project tests.</p>
                          </div>
                        </div>
                        <div className="approval">
                          <span>REVIEW THE PATCH</span>
                          <strong>Apply verified change? [y/N]</strong>
                        </div>
                        <p className="terminal-hint">
                          LLM proposals support plain JS with Node tests; TS
                          repairs are unsupported.
                        </p>
                      </>
                    ),
                  },
                ]}
              />
              <div className="terminal-footer">
                <span>
                  <span className="status-dot" aria-hidden="true"></span>{" "}
                  Offline static checks
                </span>
                <span>Illustrative sample</span>
              </div>
            </div>
            <p className="product-caption">
              <span aria-hidden="true">
                <TurnIcon />
              </span>{" "}
              Evidence first. Your approval before application.
            </p>
          </div>
        </section>

        <div className="stack-strip wrap">
          <p>
            Fits the way
            <br />
            you already build.
          </p>
          <div>
            <span>
              <b className="language-icon" aria-hidden="true">
                Py
              </b>{" "}
              Python
            </span>
            <span>
              <b className="language-icon" aria-hidden="true">
                JS
              </b>{" "}
              JavaScript
            </span>
            <span>
              <b className="language-icon" aria-hidden="true">
                TS
              </b>{" "}
              TypeScript
            </span>
            <span>
              <b className="git-icon" aria-hidden="true">
                ◇
              </b>{" "}
              Git repositories
            </span>
          </div>
        </div>

        <section
          id="workflow"
          className="workflow wrap section"
          aria-labelledby="workflow-title"
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">01 / THE WORKFLOW</p>
              <h2 id="workflow-title">
                From “what if”
                <br />
                to <span className="serif">what’s next.</span>
              </h2>
            </div>
            <p>
              Three steps, one local workflow. Go from a source pattern to
              evidence, then decide what deserves a change.
            </p>
          </div>
          <div className="steps">
            <article className="step">
              <span className="step-number">
                01
                <span aria-hidden="true">
                  <ArrowIcon />
                </span>
              </span>
              <h3>Find the leads.</h3>
              <p>
                Run offline checks against a disposable source snapshot. See
                findings, coverage, and incomplete checks together.
              </p>
              <code>
                <span>$</span> ghost find
              </code>
            </article>
            <article className="step">
              <span className="step-number">
                02
                <span aria-hidden="true">
                  <ArrowIcon />
                </span>
              </span>
              <h3>Make sense of them.</h3>
              <p>
                Group findings by file or rule. Open a candidate for its
                location, investigation guidance, and repair options.
              </p>
              <code>
                <span>$</span> ghost findings --group-by file
              </code>
            </article>
            <article className="step">
              <span className="step-number">
                03
                <span aria-hidden="true">
                  <ArrowIcon />
                </span>
              </span>
              <h3>Test a supported repair.</h3>
              <p>
                For supported Python literal parsers, reproduce the behavior and
                test a fix in a Git worktree. Review it before applying.
              </p>
              <code>
                <span>$</span> ghost solve &lt;finding-id&gt; --tests …
              </code>
            </article>
          </div>
        </section>

        <section
          id="coverage"
          className="coverage wrap section"
          aria-labelledby="coverage-title"
        >
          <div className="coverage-copy">
            <p className="eyebrow">02 / BUILT FOR A REAL REVIEW</p>
            <h2 id="coverage-title">
              Signal, with
              <br />
              its <span className="serif">context.</span>
            </h2>
            <p>
              A finding is a starting point. Ghost keeps the scope and evidence
              beside it, so a suspected pattern doesn’t become a promise.
            </p>
            <a
              className="text-link"
              href="https://github.com/Devesh36/ghost#what-find-checks-today"
            >
              Explore current coverage{" "}
              <span aria-hidden="true">
                <ArrowIcon />
              </span>
            </a>
            <div className="local-note">
              <img
                src="/assets/ghost-icon.svg"
                alt=""
                width="64"
                height="64"
                loading="lazy"
              />
              <p>
                <strong>Your code. Your machine.</strong>
                <br />
                Default static scans run offline.
                <br />
                Reviews stay in your local .ghost/ directory.
              </p>
            </div>
          </div>
          <div className="coverage-list">
            <article>
              <span className="coverage-symbol" aria-hidden="true">
                ⌕
              </span>
              <div>
                <h3>Python patterns, surfaced.</h3>
                <p>
                  Bandit checks patterns such as expression evaluation, shell
                  execution, unsafe deserialization, and disabled TLS
                  verification.
                </p>
              </div>
              <span className="tag">PYTHON</span>
            </article>
            <article>
              <span className="coverage-symbol" aria-hidden="true">
                &#123; &#125;
              </span>
              <div>
                <h3>Focused JavaScript &amp; TypeScript checks.</h3>
                <p>
                  Four bundled rules cover eval, dynamic Function construction,
                  selected shell calls, and disabled certificate verification.
                </p>
              </div>
              <span className="tag">JS / TS</span>
            </article>
            <article>
              <span className="coverage-symbol" aria-hidden="true">
                ↔
              </span>
              <div>
                <h3>Local access checks, when configured.</h3>
                <p>
                  Optional owner/other-user requests test configured routes in
                  an isolated worktree. These execute local app code; remote
                  reachability is not tested.
                </p>
              </div>
              <span className="tag">OPT-IN</span>
            </article>
            <article>
              <span className="coverage-symbol" aria-hidden="true">
                ≡
              </span>
              <div>
                <h3>A review you can return to.</h3>
                <p>
                  Saved evidence, file hashes, scan status, comparisons, and
                  exportable briefs. Rerun after edits to review current source.
                </p>
              </div>
              <span className="tag">LOCAL</span>
            </article>
          </div>
        </section>

        <DevelopmentPhases />

        <section className="faq wrap section" aria-labelledby="faq-title">
          <div>
            <p className="eyebrow">04 / GOOD TO KNOW</p>
            <h2 id="faq-title">
              Before you
              <br />
              <span className="serif">get started.</span>
            </h2>
            <a
              className="text-link"
              href="https://github.com/Devesh36/ghost/issues"
            >
              Ask on GitHub{" "}
              <span aria-hidden="true">
                <ArrowIcon />
              </span>
            </a>
          </div>
          <div className="faq-list">
            <details>
              <summary>
                Does Ghost send my code anywhere?
                <span aria-hidden="true">+</span>
              </summary>
              <p>
                Default security scans run offline without an LLM or a live
                application. Saved reviews stay locally. Optional AI advice uses
                the provider you configure; sharing review context is an
                explicit choice.
              </p>
            </details>
            <details>
              <summary>
                Do I need an API key?<span aria-hidden="true">+</span>
              </summary>
              <p>
                No. Security checks, saved findings, briefs, and supported
                deterministic Python repairs work without a model or API key. AI
                advice is optional.
              </p>
            </details>
            <details>
              <summary>
                Can Ghost fix every finding?<span aria-hidden="true">+</span>
              </summary>
              <p>
                Automatic repairs currently support a limited Python
                eval-to-literal-parser recipe. Ghost tests it in an isolated
                worktree and asks before applying. Optional LLM proposals can
                test one Python or plain JavaScript change with user-selected
                tests and approval. TypeScript repairs remain unsupported.
              </p>
            </details>
            <details>
              <summary>
                Does a completed scan mean my app is secure?
                <span aria-hidden="true">+</span>
              </summary>
              <p>
                No. Completed means the scoped checks finished, not that your
                application is vulnerability-free. Static findings remain
                suspected. Ghost is an early-stage tool with bounded coverage;
                use it alongside project tests and human review.{" "}
                <a href="https://github.com/Devesh36/ghost#current-limitations">
                  Read the current limitations.
                </a>
              </p>
            </details>
          </div>
        </section>
        <section
          id="install"
          className="install-section"
          aria-labelledby="install-title"
        >
          <div className="wrap install-inner">
            <div className="install-heading">
              <div>
                <p className="eyebrow">05 / GET GHOST</p>
                <h2 id="install-title">
                  Your next commit.
                  <br />A little more <span className="serif">confidence.</span>
                </h2>
              </div>
              <img
                className="install-mascot"
                src="/assets/ghost-icon.svg"
                alt=""
                width="156"
                height="156"
                loading="lazy"
              />
            </div>
            <TabbedContent
              appearance="install"
              ariaLabel="Installation method"
              tabs={[
                {
                  id: "quick",
                  label: "Quick install",
                  content: (
                    <>
                      {" "}
                      <code data-command>
                        curl -fsSL
                        https://raw.githubusercontent.com/Devesh36/ghost/main/install.sh
                        | bash
                      </code>
                      <p>
                        Uses an existing Homebrew or uv installation. Homebrew
                        installs the required tools too.
                      </p>{" "}
                    </>
                  ),
                  command:
                    "curl -fsSL https://raw.githubusercontent.com/Devesh36/ghost/main/install.sh | bash",
                },
                {
                  id: "brew",
                  label: "Homebrew",
                  content: (
                    <>
                      {" "}
                      <code data-command>
                        brew tap devesh36/ghost
                        https://github.com/Devesh36/ghost.git &amp;&amp; brew
                        install --HEAD devesh36/ghost/ghost
                      </code>
                      <p>
                        Requires Homebrew. Installs Git, Python 3.12, uv, and
                        Linux Bubblewrap through a custom tap.
                      </p>{" "}
                    </>
                  ),
                  command:
                    "brew tap devesh36/ghost https://github.com/Devesh36/ghost.git && brew install --HEAD devesh36/ghost/ghost",
                },
                {
                  id: "uv",
                  label: "uv",
                  content: (
                    <>
                      {" "}
                      <code data-command>
                        uv tool install --python 3.12
                        git+https://github.com/Devesh36/ghost.git &amp;&amp; uv
                        tool update-shell
                      </code>
                      <p>
                        Requires uv, Git, and your OS sandbox. Open a new
                        terminal if PATH was updated.
                      </p>{" "}
                    </>
                  ),
                  command:
                    "uv tool install --python 3.12 git+https://github.com/Devesh36/ghost.git && uv tool update-shell",
                },
              ]}
            />
            <div className="install-bottom">
              <div>
                <span className="install-check" aria-hidden="true">
                  <TurnIcon />
                </span>
                <p>
                  Inside your Git project:
                  <br />
                  <code>
                    ghost doctor <span>→</span> ghost find <span>→</span> ghost
                    brief
                  </code>
                </p>
              </div>
              <a href="https://github.com/Devesh36/ghost/blob/main/install.sh">
                Inspect the installer{" "}
                <span aria-hidden="true">
                  <ArrowIcon />
                </span>
              </a>
            </div>
            <p className="install-requirements">
              macOS / Linux · Git repository with an initial commit ·
              Development version from main
              <br />
              Python repairs require your project’s test dependencies in Ghost’s
              environment.{" "}
              <a href="/docs#installation">
                Installation guide <ArrowIcon />
              </a>
            </p>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
