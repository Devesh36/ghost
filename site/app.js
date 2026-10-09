/* Independently authored progressive enhancement; no analytics or network calls. */
"use strict";

document.querySelectorAll("[data-tabs]").forEach((group) => {
  const tabs = [...group.querySelectorAll('[role="tab"]')];
  const panels = [...group.querySelectorAll('[role="tabpanel"]')];
  const copy = group.querySelector("[data-copy]");
  const status = group.querySelector('[role="status"]');
  let resetTimer;

  function resetCopy() {
    clearTimeout(resetTimer);
    if (copy) copy.querySelector("span").textContent = "Copy command";
    if (status) status.textContent = "";
  }

  function selectTab(tab, focus = false) {
    resetCopy();
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
    });
    panels.forEach((panel) => {
      panel.hidden = panel.id !== tab.getAttribute("aria-controls");
    });
    if (focus) tab.focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== undefined) {
        event.preventDefault();
        selectTab(tabs[next], true);
      }
    });
  });

  if (copy) {
    copy.addEventListener("click", async () => {
      const panel = panels.find((item) => !item.hidden);
      const command = panel.querySelector("[data-command]");
      copy.disabled = true;
      try {
        await navigator.clipboard.writeText(command.textContent.trim());
        // Do not attach feedback to a different method selected during copying.
        if (!panel.hidden) {
          copy.querySelector("span").textContent = "Copied!";
          status.textContent = "Install command copied. Paste it in your terminal.";
          resetTimer = setTimeout(resetCopy, 5000);
        }
      } catch {
        if (!panel.hidden) {
          const range = document.createRange();
          range.selectNodeContents(command);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          status.textContent = "Clipboard unavailable. The command is selected; copy it manually.";
        }
      } finally {
        copy.disabled = false;
      }
    });
  }
  group.querySelectorAll("[data-enhance]").forEach((element) => {
    element.hidden = false;
  });
});
