import { TabbedContent } from "./tabbed-content";
import { ArrowIcon } from "./icons";

const methods = [
  {
    id: "uv",
    label: "uv",
    command:
      "uv tool install --python 3.12 git+https://github.com/Devesh36/ghost.git && uv tool update-shell",
    description:
      "Requires uv, Git, and your OS sandbox. Open a new terminal if PATH was updated.",
  },
  {
    id: "brew",
    label: "Homebrew",
    command:
      "brew tap devesh36/ghost https://github.com/Devesh36/ghost.git && brew install --HEAD devesh36/ghost/ghost",
    description:
      "Installs Git, Python 3.12, uv, and Linux Bubblewrap through the Ghost tap.",
  },
  {
    id: "quick",
    label: "Install script",
    command:
      "curl -fsSL https://raw.githubusercontent.com/Devesh36/ghost/main/install.sh | bash",
    description:
      "Uses an existing Homebrew or uv installation. Inspect the installer before running it.",
  },
];

export function InstallGhost() {
  return (
    <section
      id="install"
      className="install-section wrap section"
      aria-labelledby="install-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">GET STARTED</p>
          <h2 id="install-title">Install. Open your repo. Review.</h2>
        </div>
        <a className="text-link" href="/docs#installation">
          Installation guide <ArrowIcon />
        </a>
      </div>
      <TabbedContent
        appearance="install"
        ariaLabel="Installation method"
        tabs={methods.map((method) => ({
          ...method,
          content: (
            <>
              <code data-command>{method.command}</code>
              <p>{method.description}</p>
            </>
          ),
        }))}
      />
      <div className="install-bottom">
        <div>
          <p>Then, inside your Git project:</p>
          <code>
            ghost doctor <span>→</span> ghost repl
          </code>
        </div>
        <a href="https://github.com/Devesh36/ghost/blob/main/install.sh">
          View installer source <ArrowIcon />
        </a>
      </div>
      <p className="install-requirements">
        Development version from main. Python 3.12+, a committed Git repository,
        and macOS sandbox-exec or Linux Bubblewrap. Default scans run offline
        after installation.
      </p>
    </section>
  );
}
