import type { Metadata } from "next";
import { CommandBlock } from "../../components/command-block";
import { SiteHeader, SiteFooter } from "../../components/site-navigation";
import { ArrowIcon } from "../../components/icons";

export const metadata: Metadata = {
  title: "Ghost docs — Install, review, and fix in your project",
  description:
    "Install Ghost on macOS or Linux, use it in any Git repository, review findings, chat, and test changes before approval. Includes terminal screenshots.",
  openGraph: {
    title: "Ghost documentation",
    description:
      "From installation to your first review, with terminal walkthroughs and tested changes you approve.",
    type: "website",
  },
};

const sections = [
  ["overview", "Start here"],
  ["installation", "Install Ghost"],
  ["your-project", "Use in your project"],
  ["first-review", "Your first review"],
  ["chat-and-fix", "Chat & fix"],
  ["support", "Supported workflows"],
  ["terminal-gallery", "Terminal gallery"],
  ["updates", "Update & uninstall"],
  ["troubleshooting", "Troubleshooting"],
];

const screenshots = [
  {
    id: "workspace",
    title: "Your interactive workspace",
    command: "ghost repl",
    file: "01-repl",
    width: 1238,
    height: 734,
    alt: "Ghost REPL welcome screen with a sample project, daily review workflow, and command prompt",
    description:
      "Open the optional REPL inside your repository. Watching is opt-in with watch; standalone ghost chat works without its watcher.",
  },
  {
    id: "command-picker",
    title: "Discover commands",
    command: "/",
    file: "02-commands",
    width: 1238,
    height: 1612,
    alt: "Ghost slash-command picker listing security review, repair, and session commands",
    description:
      "Inside the REPL, type / to browse commands. Use arrow keys to select, Enter to insert, then Enter again to run.",
  },
  {
    id: "findings",
    title: "Inspect suspected findings",
    command: "ghost find",
    file: "03-findings",
    width: 1238,
    height: 1148,
    alt: "Ghost security review showing Python and TypeScript evaluation candidates, locations, rule IDs, and suspected evidence state",
    description:
      "An executed sample scan found evaluation patterns in Python and TypeScript. These are static leads; exploitability was not tested.",
  },
  {
    id: "python-repair",
    title: "Review a supported Python repair",
    command: "ghost solve <id> --tests 'python -m unittest discover -v'",
    file: "04-verified-repair",
    width: 1238,
    height: 685,
    alt: "Ghost Python repair showing original and patched security probes, three passing project tests, a code diff, and approval prompt",
    description:
      "The sample recipe reproduced function-call evaluation, rejected it after the patch, preserved three literal inputs, and passed three tests. This is helper-level proof; application reachability is unproven. Application was declined.",
  },
];

export default function Docs() {
  return (
    <>
      <SiteHeader docs />
      <main id="main" className="docs-shell wrap">
        <aside className="docs-sidebar">
          <p className="eyebrow">DOCUMENTATION</p>
          <nav className="docs-desktop-toc" aria-label="Documentation sections">
            {sections.map(([id, label], index) => (
              <a key={id} href={`#${id}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {label}
              </a>
            ))}
          </nav>
          <details className="docs-mobile-toc">
            <summary>On this page</summary>
            <nav aria-label="Mobile documentation sections">
              {sections.map(([id, label], index) => (
                <a key={id} href={`#${id}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {label}
                </a>
              ))}
            </nav>
          </details>
          <a
            className="docs-source"
            href="https://github.com/Devesh36/ghost/tree/main/docs"
          >
            More technical guides <ArrowIcon />
          </a>
        </aside>

        <div className="docs-content">
          <section
            id="overview"
            className="docs-intro docs-section"
            aria-labelledby="docs-title"
          >
            <p className="eyebrow">
              <span className="status-dot" aria-hidden="true" /> FROM INSTALL TO
              YOUR FIRST FIX
            </p>
            <h1 id="docs-title">
              Make Ghost part
              <br />
              of <span className="serif">your workflow.</span>
            </h1>
            <p className="docs-lead">
              Install once. Open your project. Find the leads, inspect the
              evidence, and decide what to change.
            </p>
            <div className="docs-facts">
              <span>macOS &amp; Linux</span>
              <span>Python 3.12+</span>
              <span>Git repositories</span>
            </div>
            <div className="docs-callout">
              <strong>Start locally. Add AI when you want it.</strong>
              <p>
                Default scans need no API key. Findings and reviews stay in your
                project’s <code>.ghost/</code> directory. Optional LLM
                assistance shares the context or source you select with your
                configured provider.
              </p>
            </div>
            <a className="text-link" href="#installation">
              Install Ghost <span aria-hidden="true">↓</span>
            </a>
          </section>

          <section
            id="installation"
            className="docs-section"
            aria-labelledby="installation-title"
          >
            <p className="eyebrow">01 / SET UP YOUR SYSTEM</p>
            <h2 id="installation-title">Install Ghost.</h2>
            <p>
              You need Git, Python 3.12 or newer, and macOS{" "}
              <code>sandbox-exec</code> or Linux Bubblewrap for isolated scans
              and experiments. Installation downloads dependencies; default
              static scans run offline afterward. These commands install the
              development version from <code>main</code>.
            </p>
            <h3>With uv — macOS or Linux</h3>
            <p>
              Already have{" "}
              <a href="https://docs.astral.sh/uv/getting-started/installation/">
                uv
              </a>{" "}
              and Git? Install Ghost as a user tool, then open a new terminal if
              PATH was updated.
            </p>
            <CommandBlock
              label="Install with uv"
              command={
                'uv tool install --python 3.12 "git+https://github.com/Devesh36/ghost.git@main"\nuv tool update-shell'
              }
            />
            <p>
              On Ubuntu/Debian, install the required sandbox first. On other
              Linux distributions, use your package manager’s Bubblewrap
              package.
            </p>
            <CommandBlock
              label="Linux sandbox · Ubuntu/Debian"
              command={"sudo apt install bubblewrap"}
            />
            <h3>With Homebrew</h3>
            <p>
              Homebrew installs Ghost and its required dependencies in a
              dedicated environment. On older Intel Macs, dependency builds can
              take time; the uv option can be more convenient.
            </p>
            <CommandBlock
              label="Install with Homebrew"
              command={
                "brew tap devesh36/ghost https://github.com/Devesh36/ghost.git && brew install --HEAD devesh36/ghost/ghost"
              }
            />
            <h3>Check your installation</h3>
            <CommandBlock
              label="Check the installed command"
              command={"ghost --help"}
            />
            <p>
              Windows users can try a Linux environment such as WSL2; native
              Windows execution is unsupported. Run <code>ghost doctor</code>{" "}
              inside your repository to check storage, tools, and confinement
              before experiments.
            </p>
          </section>

          <section
            id="your-project"
            className="docs-section"
            aria-labelledby="project-title"
          >
            <p className="eyebrow">02 / CHOOSE A REPOSITORY</p>
            <h2 id="project-title">Your project is the context.</h2>
            <p>
              You do not need to copy Ghost’s source into your application. Run
              it from the Git repository you want to review. Switch repositories
              by changing directories; each project keeps its own local history.
            </p>
            <CommandBlock
              label="Open your project"
              command={
                "cd ~/projects/my-app\ngit rev-parse --show-toplevel\ngit rev-parse --verify HEAD\nghost doctor\nghost scope"
              }
            />
            <p>
              The repository needs an initial commit. If it is a new project,
              create one using your normal Git workflow before running Ghost.
              Add <code>.ghost/</code> to that project’s <code>.gitignore</code>
              ; it contains local reviews, provider settings, and experiment
              data.
            </p>
            <details className="docs-details">
              <summary>Python project tests: use the same environment</summary>
              <p>
                A global Ghost installation cannot automatically see your
                project’s Python dependencies. For Python repairs, install Ghost
                into the environment that already contains your project and test
                dependencies.
              </p>
              <CommandBlock
                label="Install in an existing Python project environment"
                command={
                  'uv pip install --python .venv/bin/python "git+https://github.com/Devesh36/ghost.git@main"\n.venv/bin/ghost doctor\n.venv/bin/ghost fix "your requested change" --path app/parser.py --tests "python -m pytest -q" --llm'
                }
              />
              <p>
                This assumes <code>.venv</code> already exists and contains your
                project’s dependencies and pytest. Ghost pins Python test
                execution to its own interpreter.
              </p>
            </details>
          </section>

          <section
            id="first-review"
            className="docs-section"
            aria-labelledby="review-title"
          >
            <p className="eyebrow">03 / FIND &amp; UNDERSTAND</p>
            <h2 id="review-title">Run your first review.</h2>
            <CommandBlock
              label="Review the current repository"
              command={"ghost scope\nghost find\nghost brief\nghost findings"}
            />
            <ol className="docs-workflow">
              <li>
                <strong>Scope.</strong> See selected files, exclusions, and
                unsupported languages.
              </li>
              <li>
                <strong>Find.</strong> Run Python and bundled
                JavaScript/TypeScript static checks and save the review.
              </li>
              <li>
                <strong>Brief.</strong> Read priorities, scan status, and next
                steps from that saved snapshot.
              </li>
              <li>
                <strong>Findings.</strong> Inspect locations, rule IDs, and
                evidence. Use <code>ghost findings --id &lt;id&gt;</code> for
                one candidate.
              </li>
            </ol>
            <p>
              For a guided scan and repair conversation, use{" "}
              <code>ghost review</code>. It asks about LLM assistance and repair
              approval. To try a disposable sample first, use{" "}
              <code>ghost demo --security</code>; its approved repair applies
              only to the generated sample.
            </p>
            <div className="docs-callout">
              <strong>A finding is a lead, not a confirmed exploit.</strong>
              <p>
                Static candidates remain suspected. A saved brief does not
                recheck current source. Rerun <code>ghost find</code> after
                edits. Exit code 0 means completed scoped checks without
                reported findings; 1 means findings or configured access
                failures need review; 2 means incomplete or blocked checks.
              </p>
            </div>
          </section>

          <section
            id="chat-and-fix"
            className="docs-section"
            aria-labelledby="chat-title"
          >
            <p className="eyebrow">04 / ASK GHOST</p>
            <h2 id="chat-title">Ordinary prompts. Useful actions.</h2>
            <p>
              Start a conversation without the REPL watcher, or give Ghost a
              one-shot local request. Explicit scan and read requests need no
              model connection.
            </p>
            <CommandBlock
              label="Chat or request a local action"
              command={
                'ghost chat\nghost chat "scan this project"\nghost ask "show my findings"'
              }
            />
            <p>
              For less direct requests, connect an AI provider. Codex uses your
              installed CLI login. Other options include Claude Code, Claude,
              OpenAI, OpenRouter, Ollama, and compatible APIs; see{" "}
              <code>ghost connect --help</code>.
            </p>
            <CommandBlock
              label="Connect your installed Codex CLI"
              command={"ghost connect codex\nghost connect codex --check"}
            />
            <p>
              AI chat sends your prompt and conversation to the configured
              provider; it does not automatically share source or logs. A model
              can propose a bounded Ghost workflow. In an ongoing chat, say{" "}
              <strong>“do that for me”</strong> to run it or{" "}
              <strong>“cancel”</strong> to discard it. Offers expire after five
              minutes and are not saved across processes. A one-shot offer
              prints a Ghost command you can run explicitly. Model-written shell
              commands and flags are never executed.
            </p>
            <h3>Request a tested change</h3>
            <CommandBlock
              label="Request a change interactively"
              command={'ghost fix "your requested change"'}
            />
            <p>
              Ghost asks you to select one application file and an explicit test
              command, consent to sharing the selected source with your LLM,
              inspect the diff and test evidence, then approve application.
              Answering no keeps your source unchanged.
            </p>
            <CommandBlock
              label="Plain JavaScript · explicit file and tests"
              command={
                'ghost fix "Accept JSON without evaluating expressions" \\\n  --path parser.cjs --tests "node --test test/parser.test.cjs" --llm'
              }
            />
            <p>
              <code>--llm</code> opts into source sharing. In an interactive
              terminal, Ghost asks before applying; without interactive input,
              it saves the tested proposal. <code>--apply</code> is explicit
              application approval and only takes effect after all gates pass.
            </p>
            <div className="docs-callout">
              <strong>Tested is different from security-verified.</strong>
              <p>
                A passing suite and static rescan do not prove the requested
                behavior or security. Choose tests that exercise the changed
                behavior and review the diff. Fix currently changes one existing
                file; creating files, editing tests, and repairing a failing
                baseline suite are unsupported.
              </p>
            </div>
            <p>
              For model advice with saved metadata, use{" "}
              <code>ghost ask --context "Explain my latest review"</code> or{" "}
              <code>ghost ask --finding &lt;id&gt; "Explain this risk"</code>.
              These modes are advisory-only. <code>--advice-only</code> also
              disables chat actions.
            </p>
          </section>

          <section
            id="support"
            className="docs-section"
            aria-labelledby="support-title"
          >
            <p className="eyebrow">05 / KNOW THE BOUNDARIES</p>
            <h2 id="support-title">What is supported?</h2>
            <div
              className="docs-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Support matrix; scroll horizontally on small screens"
            >
              <table className="docs-table">
                <thead>
                  <tr>
                    <th scope="col">Workflow</th>
                    <th scope="col">Support</th>
                    <th scope="col">Evidence &amp; limits</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Static review</th>
                    <td>Python, JavaScript, TypeScript</td>
                    <td>
                      Bandit and four bundled JS/TS rules. Candidates remain
                      suspected.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Deterministic repair</th>
                    <td>Bounded Python literal-parser recipe</td>
                    <td>
                      <code>ghost solve &lt;id&gt; --tests COMMAND</code>;
                      helper-level security probe plus project tests.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">LLM Python proposal</th>
                    <td>Python .py with pytest or unittest</td>
                    <td>
                      Explicit command; complete passing baseline and patched
                      results; compares passing counts.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">LLM JavaScript proposal</th>
                    <td>Plain .js, .mjs, .cjs with Node 20.10+</td>
                    <td>
                      <code>node --test &lt;one JS test file&gt;</code>; flat
                      unique tests with matching ordered identities and counts.
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Other repair runners</th>
                    <td>
                      TypeScript, JSX/TSX, Jest, Vitest, npm scripts:
                      unsupported
                    </td>
                    <td>
                      Blocked before requesting a patch. A passing Python suite
                      cannot validate a JavaScript or TypeScript repair.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p>
              Verification rejects zero-test, incomplete, timed-out, failed,
              skipped, cancelled, TODO, or detectably reduced test runs. Source
              freshness, snapshot integrity, OS confinement, and static rescans
              must pass. No runner installs packages or enables network access
              for verification.
            </p>
          </section>

          <section
            id="terminal-gallery"
            className="docs-section"
            aria-labelledby="gallery-title"
          >
            <p className="eyebrow">06 / SEE IT IN THE TERMINAL</p>
            <h2 id="gallery-title">The workflow, on screen.</h2>
            <p>
              The terminal captures are from executed, disposable sample
              repositories, including a separate saved brief. They show an
              earlier interface snapshot; current wording may differ. Open an
              image for full resolution or view its presentation version.
            </p>
            <div className="docs-gallery">
              {screenshots.map((shot) => (
                <figure key={shot.id} id={`screenshot-${shot.id}`}>
                  <figcaption>
                    <span className="docs-image-kind">REAL SAMPLE CAPTURE</span>
                    <h3>{shot.title}</h3>
                    <code>{shot.command}</code>
                    <p>{shot.description}</p>
                  </figcaption>
                  <a
                    className="docs-image-link"
                    href={`/assets/screenshots/${shot.file}-terminal.png`}
                    aria-label={`Open ${shot.title.toLowerCase()} screenshot at full resolution`}
                  >
                    <img
                      src={`/assets/screenshots/${shot.file}-terminal.png`}
                      width={shot.width}
                      height={shot.height}
                      alt={shot.alt}
                      loading="lazy"
                    />
                  </a>
                  <div className="docs-image-links">
                    <a href={`/assets/screenshots/${shot.file}-terminal.png`}>
                      Full-resolution terminal capture <ArrowIcon />
                    </a>
                    <a href={`/assets/screenshots/${shot.file}.png`}>
                      Presentation version <ArrowIcon />
                    </a>
                  </div>
                </figure>
              ))}
              <figure id="screenshot-brief">
                <figcaption>
                  <span className="docs-image-kind">REAL SAMPLE CAPTURE</span>
                  <h3>Read a saved security brief</h3>
                  <code>ghost brief</code>
                  <p>
                    This separate two-file Python/TypeScript sample contains two
                    suspected static leads. Local access was not tested, and the
                    saved brief does not recheck current source.
                  </p>
                </figcaption>
                <a
                  className="docs-image-link"
                  href="/assets/screenshots/brief-preview.svg"
                  aria-label="Open the saved security brief capture at full resolution"
                >
                  <img
                    src="/assets/screenshots/brief-preview.svg"
                    width="1190"
                    height="1002"
                    alt="Actual Ghost saved security brief with two suspected medium findings, scan scope, source snapshot details, and next steps"
                    loading="lazy"
                  />
                </a>
                <div className="docs-image-links">
                  <a href="/assets/screenshots/brief-preview.svg">
                    Full-resolution terminal capture <ArrowIcon />
                  </a>
                </div>
              </figure>
              <figure id="screenshot-chat">
                <figcaption>
                  <span className="docs-image-kind">ILLUSTRATIVE DEMO</span>
                  <h3>Ask, scan, and prepare a tested change</h3>
                  <code>ghost chat</code>
                  <p>
                    This generated illustration shows a condensed chat scan and
                    requested JavaScript change. Its example test counts do not
                    establish security or model quality; source sharing and
                    application need approval.
                  </p>
                </figcaption>
                <a
                  className="docs-image-link"
                  href="/assets/screenshots/06-chat-illustration.png"
                  aria-label="Open the illustrated chat workflow at full resolution"
                >
                  <img
                    src="/assets/screenshots/06-chat-illustration.png"
                    width="1586"
                    height="992"
                    alt="Illustrated Ghost chat scanning a demo project and showing a suspected finding beside a tested JavaScript proposal awaiting approval"
                    loading="lazy"
                  />
                </a>
                <div className="docs-image-links">
                  <a href="/assets/screenshots/06-chat-illustration.png">
                    Full-resolution illustration <ArrowIcon />
                  </a>
                </div>
              </figure>
              <figure id="screenshot-fix">
                <figcaption>
                  <span className="docs-image-kind">ILLUSTRATIVE DEMO</span>
                  <h3>A requested change, tested before approval</h3>
                  <code>ghost fix "the changes"</code>
                  <p>
                    This generated illustration condenses the fix workflow:
                    select source and tests, consent to LLM assistance, inspect
                    a tested diff, then decide whether to apply. It is not a
                    live terminal capture or evidence of model quality.
                  </p>
                </figcaption>
                <a
                  className="docs-image-link"
                  href="/assets/screenshots/05-fix-illustration.png"
                  aria-label="Open the illustrated fix workflow at full resolution"
                >
                  <img
                    src="/assets/screenshots/05-fix-illustration.png"
                    width="1536"
                    height="1024"
                    alt="Illustrated Ghost fix command selecting a JavaScript file and Node tests, displaying a diff and two passing tests, then declining application"
                    loading="lazy"
                  />
                </a>
                <div className="docs-image-links">
                  <a href="/assets/screenshots/05-fix-illustration.png">
                    Full-resolution illustration <ArrowIcon />
                  </a>
                </div>
              </figure>
            </div>
          </section>

          <section
            id="updates"
            className="docs-section"
            aria-labelledby="updates-title"
          >
            <p className="eyebrow">07 / KEEP IT CURRENT</p>
            <h2 id="updates-title">Update or remove Ghost.</h2>
            <CommandBlock
              label="Update a uv installation from main"
              command={
                'uv tool install --force --reinstall --refresh --python 3.12 "git+https://github.com/Devesh36/ghost.git@main"'
              }
            />
            <CommandBlock
              label="Update a Homebrew HEAD installation"
              command={
                "brew update\nbrew upgrade --fetch-HEAD devesh36/ghost/ghost"
              }
            />
            <p>
              Remove the installation with{" "}
              <code>uv tool uninstall ghost-debugger</code> or{" "}
              <code>brew uninstall devesh36/ghost/ghost</code>, depending on how
              you installed it. Uninstalling leaves each project’s{" "}
              <code>.ghost/</code> history in place.
            </p>
          </section>

          <section
            id="troubleshooting"
            className="docs-section"
            aria-labelledby="troubleshooting-title"
          >
            <p className="eyebrow">08 / GET UNBLOCKED</p>
            <h2 id="troubleshooting-title">Common setup questions.</h2>
            <details className="docs-details">
              <summary>“ghost: command not found”</summary>
              <p>
                For uv, run <code>uv tool update-shell</code>, open a new
                terminal, and try <code>ghost --help</code>.{" "}
                <code>uv tool dir --bin</code> shows the executable directory;
                you can run Ghost from that full path.
              </p>
            </details>
            <details className="docs-details">
              <summary>“No Git repository” or missing HEAD</summary>
              <p>
                Change into the project directory and check{" "}
                <code>git rev-parse --show-toplevel</code>. Ghost needs an
                initial commit. Create one deliberately using your normal Git
                workflow; Ghost does not create it for you.
              </p>
            </details>
            <details className="docs-details">
              <summary>Homebrew appears paused on an older Intel Mac</summary>
              <p>
                Homebrew may be updating itself, waiting for installation
                confirmation, or building dependencies from source. Review its
                output and progress. If you prefer uv, use the explicit uv
                instructions above and check your Git and sandbox prerequisites.
              </p>
            </details>
            <details className="docs-details">
              <summary>Confinement or Node is missing</summary>
              <p>
                Run <code>ghost doctor</code>. Linux needs Bubblewrap; macOS
                needs <code>sandbox-exec</code>. JavaScript proposals need Node
                20.10+ on PATH. Install the missing runtime yourself and retry.
                Keep confinement enabled; disabling it does not qualify a
                repair.
              </p>
            </details>
            <details className="docs-details">
              <summary>
                Tests cannot import my Python project or dependencies
              </summary>
              <p>
                Install Ghost in your project’s Python environment, including
                its test dependencies. Ghost does not silently install packages.
                Use explicit pytest/unittest commands; a global tool environment
                does not inherit the project’s virtual environment.
              </p>
            </details>
            <details className="docs-details">
              <summary>A proposal is blocked, or the finding is stale</summary>
              <p>
                Inspect the reported gate in <code>ghost solution</code>. Rerun{" "}
                <code>ghost find</code> after source changes. Select a supported
                runner and tests that pass at baseline, include real cases, and
                do not mutate project files. Ghost does not apply a blocked
                proposal.
              </p>
            </details>
            <p className="docs-help-link">
              Need more detail?{" "}
              <a href="https://github.com/Devesh36/ghost/tree/main/docs">
                Read the technical guides <ArrowIcon />
              </a>{" "}
              or{" "}
              <a href="https://github.com/Devesh36/ghost/issues">
                open an issue
              </a>
              .
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
