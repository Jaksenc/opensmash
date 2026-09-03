let activeLockCount = 0;
let lockedPageState = null;
const unlockListeners = new Set();

const ROOT_LOCK_STYLES = Object.freeze({
  "overflow-x": "hidden",
  "overflow-y": "hidden",
  "overscroll-behavior": "none",
  "scroll-behavior": "auto",
});

const BODY_LOCK_STYLES = Object.freeze({
  position: "fixed",
  width: "100%",
  "overflow-x": "hidden",
  "overflow-y": "hidden",
  "overscroll-behavior": "none",
});

function captureStyle(element, property) {
  return {
    element,
    property,
    priority: element.style.getPropertyPriority(property),
    value: element.style.getPropertyValue(property),
  };
}

function restoreStyle({ element, property, priority, value }) {
  if (value) element.style.setProperty(property, value, priority);
  else element.style.removeProperty(property);
}

function applyStyles(element, styles, capturedStyles) {
  for (const [property, value] of Object.entries(styles)) {
    capturedStyles.push(captureStyle(element, property));
    element.style.setProperty(property, value);
  }
}

function lockPage() {
  const root = document.documentElement;
  const body = document.body;
  const scrollX = window.scrollX || window.pageXOffset || 0;
  const scrollY = window.scrollY || window.pageYOffset || 0;
  const capturedStyles = [];

  applyStyles(root, ROOT_LOCK_STYLES, capturedStyles);
  applyStyles(body, BODY_LOCK_STYLES, capturedStyles);
  applyStyles(body, {
    left: `${-scrollX}px`,
    top: `${-scrollY}px`,
  }, capturedStyles);

  return { capturedStyles, root, scrollX, scrollY };
}

function unlockPage({ capturedStyles, root, scrollX, scrollY }) {
  // Keep scroll restoration instantaneous even though the site normally uses
  // smooth scrolling. Restoring a fixed body otherwise visibly glides from
  // the top of the page back to the user's previous position.
  const rootScrollBehavior = capturedStyles.find(
    (style) => style.element === root && style.property === "scroll-behavior",
  );

  for (const style of capturedStyles) {
    if (style !== rootScrollBehavior) restoreStyle(style);
  }
  root.style.setProperty("scroll-behavior", "auto");
  window.scrollTo(scrollX, scrollY);
  if (rootScrollBehavior) restoreStyle(rootScrollBehavior);
}

/**
 * Freeze the document in place until the returned release function is called.
 * Locking the body with fixed positioning is intentional: overflow alone does
 * not reliably stop the root scroller in mobile Safari.
 */
export function lockPageScroll() {
  if (typeof document === "undefined" || typeof window === "undefined" || !document.body) {
    return () => {};
  }

  if (activeLockCount === 0) lockedPageState = lockPage();
  activeLockCount += 1;
  let released = false;

  return () => {
    if (released) return;
    released = true;
    activeLockCount -= 1;
    if (activeLockCount > 0 || !lockedPageState) return;

    const pageState = lockedPageState;
    lockedPageState = null;
    unlockPage(pageState);
    unlockListeners.forEach((listener) => listener());
  };
}

export function isPageScrollLocked() {
  return activeLockCount > 0;
}

export function onPageScrollUnlock(listener) {
  unlockListeners.add(listener);
  return () => unlockListeners.delete(listener);
}
