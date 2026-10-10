import dimensions from "../content/terminal-gallery.json";
import { TabbedContent } from "./tabbed-content";
import { ArrowIcon } from "./icons";

const captures = [
  {
    file: "01-repl",
    label: "Workspace",
    title: "Start in your own repository.",
    command: "ghost repl",
    description:
      "The REPL workspace groups the project, branch, and next local review step. The interactive footer explains commands and options as you type. Watching starts only when you request it.",
    alt: "Ghost workspace with the demo repository, main branch, and first review instructions",
  },
  {
    file: "02-commands",
    label: "Commands",
    title: "Find the command you need.",
    command: "help · inside ghost repl",
    description:
      "The REPL’s current help groups commands by purpose: start, security, observation, investigation, and optional AI.",
    alt: "Ghost command help grouped by local review, repair, observation, and optional AI workflows",
  },
  {
    file: "05-brief",
    label: "Brief",
    title: "Read the evidence before acting.",
    command: "ghost brief",
    description:
      "A saved brief from a real two-language sample scan. Both evaluation patterns are suspected leads; local access and application exploitability were not tested.",
    alt: "Ghost saved security brief with completed scoped checks and two suspected evaluation findings",
  },
  {
    file: "03-findings",
    label: "Findings",
    title: "Keep the finding and its scope together.",
    command: "ghost find",
    description:
      "Bandit and Ghost’s bundled Semgrep rules executed against a disposable Python and TypeScript sample. Read coverage and evidence alongside the candidates.",
    alt: "Current Ghost scan output with Python and TypeScript evaluation candidates, scanner coverage, and evidence limits",
  },
  {
    file: "04-verified-repair",
    label: "Repair",
    title: "A repair you can inspect before applying.",
    command: "ghost solve <id> --tests 'python -m unittest discover -v'",
    description:
      "The sample’s Python recipe reproduced function-call evaluation, rejected it after the patch, preserved three literal cases, and passed three project tests. The proposal was not applied; application reachability remains unproven.",
    alt: "Executed Python repair with baseline and patched tests, helper-level proof, and an unapplied diff",
  },
  {
    file: "06-chat",
    label: "Chat",
    title: "Plain language. A local action.",
    command: 'ghost chat "summarize the findings"',
    description:
      "Ghost routed this explicit request to the real saved-brief workflow. No model connection or model-generated results were used.",
    alt: "Ghost chat routing summarize the findings to the real local brief action and displaying saved review evidence",
  },
] as const;

export function TerminalGallery() {
  return (
    <div className="docs-gallery">
      <TabbedContent
        appearance="gallery"
        ariaLabel="Terminal walkthrough"
        tabs={captures.map((capture) => ({
          id: `gallery-${capture.file}`,
          label: capture.label,
          content: (
            <figure id={`screenshot-${capture.file}`}>
              <figcaption>
                <span className="docs-image-kind">
                  EXECUTED SAMPLE / GHOST THEME
                </span>
                <h3>{capture.title}</h3>
                <code>{capture.command}</code>
                <p>{capture.description}</p>
              </figcaption>
              <div
                className="docs-capture-scroll"
                role="region"
                aria-label={`${capture.label} terminal capture; scroll to read the full output`}
                tabIndex={0}
              >
                <a
                  className="docs-image-link"
                  href={`/assets/screenshots/${capture.file}-terminal.png`}
                  aria-label={`Open ${capture.label.toLowerCase()} capture at full resolution`}
                >
                  <img
                    src={`/assets/screenshots/${capture.file}-terminal.png`}
                    width={dimensions[capture.file].width}
                    height={dimensions[capture.file].height}
                    alt={capture.alt}
                    loading="lazy"
                  />
                </a>
              </div>
              <div className="docs-image-links">
                <span>Real output · same font, frame & palette</span>
                <a href={`/assets/screenshots/${capture.file}-terminal.png`}>
                  Open full capture <ArrowIcon />
                </a>
              </div>
            </figure>
          ),
        }))}
      />
    </div>
  );
}
