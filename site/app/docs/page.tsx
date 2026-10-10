import type { Metadata } from "next";
import { CommandBlock } from "../../components/command-block";
import { SiteHeader, SiteFooter } from "../../components/site-navigation";
import { ArrowIcon } from "../../components/icons";
import { DocsContents } from "../../components/docs-contents";
import { TerminalGallery } from "../../components/terminal-gallery";

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

export default function Docs() {
  return (
    <>
      <SiteHeader docs />
      <main id="main" className="docs-shell wrap">
        <DocsContents />

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
              Your first review.
              <br />
              <span className="serif">A clear next step.</span>
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
            <div className="docs-quickstart" aria-label="Choose your next step">
              <a href="#installation">
                <span>01 / SET UP</span>
                <strong>
                  Install Ghost <ArrowIcon />
                </strong>
                <p>One installation. Your own Git projects.</p>
              </a>
              <a href="#first-review">
                <span>02 / REVIEW</span>
                <strong>
                  Find the leads <ArrowIcon />
                </strong>
                <p>Scope, scan, and read the evidence.</p>
              </a>
              <a href="#chat-and-fix">
                <span>03 / CHANGE</span>
                <strong>
                  Test a proposal <ArrowIcon />
                </strong>
                <p>Inspect the diff before applying.</p>
              </a>
            </div>
            <CommandBlock
              label="Already installed? Your first review"
              command={
                "cd ~/projects/my-app\nghost doctor\nghost find\nghost brief"
              }
            />
            <a className="text-link" href="#terminal-gallery">
              See the terminal walkthrough <span aria-hidden="true">↓</span>
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
              Six fresh views from the current Ghost CLI. One theme, one
              terminal frame, and real sample output. Choose a step below;
              scroll within a capture or open it at full resolution.
            </p>
            <TerminalGallery />
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
