"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { CopyIcon } from "./icons";

type Tab = {
  id: string;
  label: string;
  content: ReactNode;
  command?: string;
};

type Props = {
  appearance: "terminal" | "install" | "gallery" | "product";
  ariaLabel: string;
  tabs: Tab[];
};

export function TabbedContent({ appearance, ariaLabel, tabs }: Props) {
  const [selected, setSelected] = useState(0);
  const [ready, setReady] = useState(false);
  const [copying, setCopying] = useState(false);
  const [feedback, setFeedback] = useState<"idle" | "copied" | "failed">(
    "idle",
  );
  const [message, setMessage] = useState("");
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const currentTab = useRef(0);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const install = appearance === "install";
  const gallery = appearance === "gallery";
  const product = appearance === "product";

  useEffect(() => {
    setReady(true);
    return () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    };
  }, []);

  function resetCopy() {
    if (resetTimer.current) clearTimeout(resetTimer.current);
    setFeedback("idle");
    setMessage("");
  }

  function selectTab(index: number, focus = false) {
    resetCopy();
    currentTab.current = index;
    setSelected(index);
    if (focus) buttons.current[index]?.focus();
  }

  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number | undefined;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft")
      next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      selectTab(next, true);
    }
  }

  async function copyCommand() {
    const index = selected;
    const tab = tabs[index];
    if (!tab.command) return;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(tab.command);
      if (currentTab.current === index) {
        setFeedback("copied");
        setMessage("Install command copied. Paste it in your terminal.");
        resetTimer.current = setTimeout(resetCopy, 5000);
      }
    } catch {
      if (currentTab.current === index) {
        const command = document
          .getElementById(`${tab.id}-panel`)
          ?.querySelector("[data-command]");
        const selection = window.getSelection();
        if (command && selection) {
          const range = document.createRange();
          range.selectNodeContents(command);
          selection.removeAllRanges();
          selection.addRange(range);
          setMessage(
            "Clipboard unavailable. The command is selected; copy it manually.",
          );
        } else {
          setMessage(
            "Clipboard unavailable. Select the command and copy it manually.",
          );
        }
        setFeedback("failed");
      }
    } finally {
      setCopying(false);
    }
  }

  const panels = tabs.map((tab, index) => (
    <div
      key={tab.id}
      id={`${tab.id}-panel`}
      role="tabpanel"
      aria-labelledby={`${tab.id}-tab`}
      tabIndex={0}
      hidden={index !== selected && (!(gallery || product) || ready)}
    >
      {tab.content}
    </div>
  ));

  return (
    <div
      className={install ? "install-box" : undefined}
      data-tabs
      data-install={install || undefined}
    >
      <div
        className={
          product
            ? "product-tabs"
            : gallery
              ? "docs-gallery-tabs"
              : install
                ? "install-tabs"
                : "terminal-tabs"
        }
        role="tablist"
        aria-label={ariaLabel}
        hidden={!ready}
      >
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            id={`${tab.id}-tab`}
            type="button"
            role="tab"
            aria-selected={index === selected}
            aria-controls={`${tab.id}-panel`}
            tabIndex={index === selected ? 0 : -1}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            onClick={() => selectTab(index)}
            onKeyDown={(event) => onTabKey(event, index)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {install ? (
        <>
          <div className="install-command">
            <div className="install-panels">{panels}</div>
            <button
              className="copy-button"
              type="button"
              data-copy
              hidden={!ready}
              disabled={copying}
              onClick={copyCommand}
            >
              <CopyIcon />
              <span>{feedback === "copied" ? "Copied!" : "Copy command"}</span>
            </button>
          </div>
          <p className="copy-status" aria-live="polite" role="status">
            {message}
          </p>
        </>
      ) : (
        <div
          className={
            product
              ? "product-panels"
              : gallery
                ? "docs-gallery-panels"
                : "terminal-content"
          }
        >
          {panels}
        </div>
      )}
    </div>
  );
}
