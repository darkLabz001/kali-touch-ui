// Reserve the keyboard's actual height so fields and terminal input stay visible.
(() => {
  const keyboard = document.getElementById("kb");
  if (!keyboard) return;
  const fitKeyboard = () => {
    document.documentElement.style.setProperty("--keyboard-height", `${keyboard.offsetHeight}px`);
    const input = document.activeElement;
    if (keyboard.offsetHeight && input && input.id !== "term-in" && /^(INPUT|TEXTAREA)$/.test(input.tagName)) {
      requestAnimationFrame(() => input.scrollIntoView({ block: "nearest" }));
    }
  };
  new ResizeObserver(fitKeyboard).observe(keyboard);
  document.addEventListener("focusin", fitKeyboard);
})();
