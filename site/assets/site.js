(() => {
  "use strict";

  const selectText = (element) => {
    const range = document.createRange();
    const selection = window.getSelection();
    range.selectNodeContents(element);
    selection.removeAllRanges();
    selection.addRange(range);
  };

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    const target = document.getElementById(button.dataset.copyTarget);
    const label = button.querySelector("[data-copy-label]");
    const liveRegion = button.closest(".command-block").querySelector(".live-region");
    const initialLabel = label.textContent;
    let resetTimer;

    const setTemporaryState = (nextLabel, announcement = "") => {
      window.clearTimeout(resetTimer);
      label.textContent = nextLabel;
      liveRegion.textContent = announcement;
      resetTimer = window.setTimeout(() => {
        label.textContent = initialLabel;
        liveRegion.textContent = "";
      }, 2000);
    };

    const manualCopy = () => {
      selectText(target);
      setTemporaryState(button.dataset.copyManualLabel, button.dataset.copyManual);
    };

    button.addEventListener("click", async () => {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        manualCopy();
        return;
      }
      try {
        await navigator.clipboard.writeText(target.textContent);
        setTemporaryState(button.dataset.copySuccess, button.dataset.copySuccess);
      } catch (_error) {
        manualCopy();
      }
    });
  });

  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const activate = (selectedTab) => {
    tabs.forEach((tab) => {
      const selected = tab === selectedTab;
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panel.hidden = !selected;
    });
    selectedTab.focus();
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      let target;
      if (event.key === "ArrowRight") target = tabs[(index + 1) % tabs.length];
      if (event.key === "ArrowLeft") target = tabs[(index - 1 + tabs.length) % tabs.length];
      if (event.key === "Home") target = tabs[0];
      if (event.key === "End") target = tabs[tabs.length - 1];
      if (target) {
        event.preventDefault();
        activate(target);
      }
    });
  });
})();
