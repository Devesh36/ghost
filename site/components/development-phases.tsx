import history from "../.generated/history.json";
import notes from "../content/development-notes.json";
import { ArrowIcon } from "./icons";

const phases = [
  {
    date: "2026-10-02",
    title: "The local debugging foundation",
    outcome:
      "From an idea to a working CLI and REPL: record commands, inspect failures, and test changes in isolated experiments.",
  },
  {
    date: "2026-10-03",
    title: "Security becomes the daily workflow",
    outcome:
      "Offline findings, a bounded Python repair recipe, and configured cross-user access checks turn debugging into a security review workflow.",
  },
  {
    date: "2026-10-04",
    title: "A terminal you can live in",
    outcome:
      "Source scope, conversational actions, provider connections, slash commands, and saved themes make the local workflow easier to navigate.",
  },
  {
    date: "2026-10-05",
    title: "Evidence you can come back to",
    outcome:
      "Saved review history, stricter verification, private persistence, and diagnostics keep evidence inspectable and protect the source being reviewed.",
  },
  {
    date: "2026-10-07",
    title: "Preparing an early-access release",
    outcome:
      "Review comparisons, sandbox inventory, and Linux/macOS qualification support a gated draft release with explicit limits.",
  },
  {
    date: "2026-10-08",
    title: "Make a review easier to act on",
    outcome:
      "Locked dependencies and saved security briefs bring repeatable development, responsive review summaries, and practical guides.",
  },
  {
    date: "2026-10-09",
    title: "Guided reviews and tested changes",
    outcome:
      "Installation, the Next.js website, grouped comparisons, transactional history upgrades, optional AI review, and explicit JavaScript test evidence connect the workflow.",
  },
  {
    date: "2026-10-10",
    title: "Open the workflow to everyone",
    outcome:
      "In-site docs, a consistent terminal gallery, and this development log explain how to use Ghost and how it is evolving.",
  },
  {
    date: "9999-12-31",
    title: "The next phase",
    outcome:
      "Continuing improvements to Ghost, recorded as new commits and development notes arrive.",
  },
];

function phaseIndex(date: string) {
  const index = phases.findIndex((phase) => date <= phase.date);
  return index === -1 ? phases.length - 1 : index;
}

function displayDate(date: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T12:00:00Z`));
}

export function DevelopmentPhases() {
  return (
    <section
      id="phases"
      className="phases wrap section"
      aria-labelledby="phases-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">BUILDING GHOST, IN PUBLIC</p>
          <h2 id="phases-title">
            Phases.
            <br />
            <span className="serif">One change at a time.</span>
          </h2>
        </div>
        <p>
          From the first local debugger to a security review you can return to.
          Follow what changed, when, and what it made possible.
        </p>
      </div>
      <div className="phase-summary">
        <span>{history.length} recorded commits</span>
        <span>Since October 2026</span>
        <span>Dates in India Standard Time</span>
      </div>
      <div className="phase-timeline">
        {phases.map((phase, index) => {
          const commits = history.filter(
            (commit) => phaseIndex(commit.date) === index,
          );
          const sessions = notes.filter(
            (note) => phaseIndex(note.date) === index,
          );
          if (!commits.length && !sessions.length) return null;
          const dates = [...commits, ...sessions]
            .map((item) => item.date)
            .sort();
          return (
            <article className="phase" key={phase.date}>
              <div className="phase-marker">
                <span>{String(index + 1).padStart(2, "0")}</span>
              </div>
              <div className="phase-content">
                <p className="phase-date">
                  <time dateTime={dates[0]}>{displayDate(dates[0])}</time>
                  {dates.at(-1) !== dates[0] && (
                    <>
                      {" "}
                      —{" "}
                      <time dateTime={dates.at(-1)}>
                        {displayDate(dates.at(-1)!)}
                      </time>
                    </>
                  )}
                </p>
                <h3>{phase.title}</h3>
                <p className="phase-outcome">{phase.outcome}</p>
                <details className="phase-record">
                  <summary>
                    Explore this phase{" "}
                    <span>
                      {commits.length} commits
                      {sessions.length
                        ? ` · ${sessions.length} development notes`
                        : ""}
                    </span>
                    <ArrowIcon />
                  </summary>
                  {sessions.length > 0 && (
                    <div className="phase-notes">
                      <h4>From development conversations</h4>
                      {sessions.map((note) => (
                        <div key={note.title}>
                          <time dateTime={note.date}>
                            {displayDate(note.date)}
                          </time>
                          <strong>{note.title}</strong>
                          <p>{note.description}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  <ol className="phase-commits">
                    {commits.map((commit) => (
                      <li key={commit.hash}>
                        <div>
                          <time dateTime={commit.date}>
                            {displayDate(commit.date)}
                          </time>
                          <a
                            href={`https://github.com/Devesh36/ghost/commit/${commit.hash}`}
                            aria-label={`View commit ${commit.hash.slice(0, 7)}: ${commit.subject}`}
                          >
                            {commit.hash.slice(0, 7)} <ArrowIcon />
                          </a>
                        </div>
                        <p>{commit.description}</p>
                        {commit.description !== commit.subject && (
                          <small>{commit.subject}</small>
                        )}
                      </li>
                    ))}
                  </ol>
                </details>
              </div>
            </article>
          );
        })}
      </div>
      <p className="phase-footnote">
        Commit records come from the repository. Development notes capture
        conversation outcomes; private chat transcripts are not published.
      </p>
    </section>
  );
}
