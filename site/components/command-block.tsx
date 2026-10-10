"use client";

import { useEffect, useRef, useState } from "react";
import { CopyIcon } from "./icons";

export function CommandBlock({
  label,
  command,
}: {
  label: string;
  command: string;
}) {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const code = useRef<HTMLElement>(null);
  useEffect(() => {
    setReady(true);
  }, []);

  async function copy() {
    setBusy(true);
    try {
      await navigator.clipboard.writeText(command);
      setStatus("Copied. Paste the command in your terminal.");
    } catch {
      const selection = window.getSelection();
      if (code.current && selection) {
        const range = document.createRange();
        range.selectNodeContents(code.current);
        selection.removeAllRanges();
        selection.addRange(range);
        setStatus("Clipboard unavailable. Command selected; copy it manually.");
      } else {
        setStatus(
          "Clipboard unavailable. Select and copy the command manually.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="docs-command">
      <div className="docs-command-bar">
        <span>{label}</span>
        <button
          type="button"
          onClick={copy}
          hidden={!ready}
          disabled={busy}
          aria-label={`Copy ${label}`}
        >
          <CopyIcon /> {status.startsWith("Copied") ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>
        <code ref={code}>{command}</code>
      </pre>
      <p className="docs-copy-status" role="status" aria-live="polite">
        {status}
      </p>
    </div>
  );
}
