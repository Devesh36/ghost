import Link from "next/link";
import { ArrowIcon } from "./icons";

export function SiteHeader({ docs = false }: { docs?: boolean }) {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="header wrap">
        <Link className="brand" href="/" aria-label="Ghost home">
          <img src="/assets/ghost-icon.svg" width="44" height="44" alt="" />
          <span>Ghost</span>
        </Link>
        <nav aria-label="Main navigation">
          <Link className="nav-secondary" href="/#workflow">
            Product
          </Link>
          <Link href="/#phases">Phases</Link>
          <Link
            className="nav-docs"
            href="/docs"
            aria-current={docs ? "page" : undefined}
          >
            Docs
          </Link>
          <a className="nav-github" href="https://github.com/Devesh36/ghost">
            GitHub <ArrowIcon />
          </a>
          <Link
            className="button button-small"
            href={docs ? "#installation" : "/#install"}
          >
            Install <ArrowIcon />
          </Link>
        </nav>
      </header>
    </>
  );
}

export function SiteFooter() {
  return (
    <footer className="footer wrap">
      <div>
        <Link className="brand" href="/" aria-label="Ghost home">
          <img src="/assets/ghost-icon.svg" width="40" height="40" alt="" />
          <span>Ghost</span>
        </Link>
        <p>Local code review. Tested changes. Your terminal.</p>
      </div>
      <div className="footer-links">
        <a href="https://github.com/Devesh36/ghost">
          GitHub <ArrowIcon />
        </a>
        <Link href="/docs">
          Documentation <ArrowIcon />
        </Link>
        <Link href="/#phases">
          Development phases <ArrowIcon />
        </Link>
        <a href="https://github.com/Devesh36/ghost/blob/main/LICENSE">
          MIT license <ArrowIcon />
        </a>
        <span>MIT open source · macOS &amp; Linux</span>
      </div>
    </footer>
  );
}
