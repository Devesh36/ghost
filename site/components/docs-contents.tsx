"use client";

import { useEffect, useState } from "react";
import { ArrowIcon } from "./icons";

const groups = [
  {
    title: "GET STARTED",
    links: [
      ["overview", "Quick start"],
      ["installation", "Install Ghost"],
      ["your-project", "Open your project"],
    ],
  },
  {
    title: "DAILY WORKFLOW",
    links: [
      ["first-review", "Review & findings"],
      ["chat-and-fix", "Chat & tested changes"],
    ],
  },
  {
    title: "REFERENCE",
    links: [
      ["terminal-gallery", "Terminal walkthrough"],
      ["support", "Supported workflows"],
      ["updates", "Update & uninstall"],
      ["troubleshooting", "Troubleshooting"],
    ],
  },
];

export function DocsContents() {
  const [active, setActive] = useState("overview");
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-10% 0px -65% 0px" },
    );
    for (const section of document.querySelectorAll(".docs-section"))
      observer.observe(section);
    return () => observer.disconnect();
  }, []);
  const links = (mobile = false) => (
    <nav
      aria-label={
        mobile ? "Mobile documentation sections" : "Documentation sections"
      }
    >
      {groups.map((group) => (
        <div className="docs-toc-group" key={group.title}>
          <p>{group.title}</p>
          {group.links.map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              aria-current={active === id ? "location" : undefined}
              onClick={(event) => {
                setActive(id);
                if (mobile)
                  event.currentTarget
                    .closest("details")
                    ?.removeAttribute("open");
              }}
            >
              {label}
            </a>
          ))}
        </div>
      ))}
    </nav>
  );
  return (
    <aside className="docs-sidebar">
      <p className="eyebrow">GHOST / DOCS</p>
      <div className="docs-desktop-toc">{links()}</div>
      <details className="docs-mobile-toc">
        <summary>
          On this page{" "}
          <span>
            {
              groups
                .flatMap((group) => group.links)
                .find(([id]) => id === active)?.[1]
            }
          </span>
        </summary>
        {links(true)}
      </details>
      <a
        className="docs-source"
        href="https://github.com/Devesh36/ghost/tree/main/docs"
      >
        Technical guides <ArrowIcon />
      </a>
    </aside>
  );
}
