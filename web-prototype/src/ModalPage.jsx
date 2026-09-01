import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_CLOSE_DURATION = 480;
const DEFAULT_FOCUS_DELAY = 680;

export default function ModalPage({
  bodyClass,
  children,
  className = "",
  closeDuration = DEFAULT_CLOSE_DURATION,
  dismissOnBackdrop = false,
  focusDelay = DEFAULT_FOCUS_DELAY,
  initialFocusRef,
  onRequestClose,
  open,
  ...props
}) {
  const [isVisible, setIsVisible] = useState(false);
  const closingRef = useRef(false);
  const closeTimerRef = useRef(null);
  const onRequestCloseRef = useRef(onRequestClose);

  useEffect(() => {
    onRequestCloseRef.current = onRequestClose;
  }, [onRequestClose]);

  const close = useCallback((complete) => {
    if (closingRef.current) return;
    closingRef.current = true;
    setIsVisible(false);
    window.clearTimeout(closeTimerRef.current);
    closeTimerRef.current = window.setTimeout(() => {
      (complete || onRequestCloseRef.current)?.();
    }, closeDuration);
  }, [closeDuration]);

  useEffect(() => {
    if (!open) {
      closingRef.current = false;
      setIsVisible(false);
      return undefined;
    }
    closingRef.current = false;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const revealFrame = window.requestAnimationFrame(() => setIsVisible(true));
    const focusTimer = window.setTimeout(() => initialFocusRef?.current?.focus(), focusDelay);
    document.body.style.overflow = "hidden";
    if (bodyClass) document.body.classList.add(bodyClass);

    const closeOnEscape = (event) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", closeOnEscape);

    return () => {
      window.cancelAnimationFrame(revealFrame);
      window.clearTimeout(focusTimer);
      window.clearTimeout(closeTimerRef.current);
      document.body.style.overflow = previousOverflow;
      if (bodyClass) document.body.classList.remove(bodyClass);
      window.removeEventListener("keydown", closeOnEscape);
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, [bodyClass, close, focusDelay, initialFocusRef, open]);

  return (
    <div
      {...props}
      className={`modal-page ${className} ${isVisible ? "is-visible" : ""}`.trim()}
      hidden={!open}
      onMouseDown={(event) => {
        if (dismissOnBackdrop && event.target === event.currentTarget) close();
      }}
    >
      {typeof children === "function" ? children(close) : children}
    </div>
  );
}
