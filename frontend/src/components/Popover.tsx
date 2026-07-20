import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

interface TriggerProps {
  ref: RefObject<HTMLButtonElement>;
  onClick: () => void;
  "aria-expanded": boolean;
  "aria-haspopup": "dialog";
  "data-open": boolean;
}

interface Props {
  /** Accessible name for the popover panel (dialog). */
  label: string;
  /** Renders the trigger button; spread the given props onto it. */
  trigger: (props: TriggerProps) => ReactNode;
  /** Panel body. Receives a `close` callback for controls that should dismiss on select. */
  children: ReactNode | ((close: () => void) => ReactNode);
  /** Horizontal edge to anchor to the trigger (default: right edge). */
  align?: "start" | "end";
  /** Preferred panel width; clamped to the viewport. */
  width?: number;
}

/**
 * Small popover rendered in a portal on `document.body` — escapes the sticky filter bar's
 * `backdrop-filter` containing block (which would otherwise clip an in-flow dropdown). Handles
 * anchored + viewport-clamped positioning, Esc / outside-click dismiss, and focus return.
 */
export function Popover({ label, trigger, children, align = "end", width = 320 }: Props) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; w: number }>({ top: 0, left: 0, w: width });

  const close = () => setOpen(false);

  function reposition() {
    const t = triggerRef.current;
    if (!t) return;
    const r = t.getBoundingClientRect();
    const w = Math.min(width, window.innerWidth - 24);
    const desiredLeft = align === "end" ? r.right - w : r.left;
    const left = Math.max(12, Math.min(desiredLeft, window.innerWidth - w - 12));
    setPos({ top: r.bottom + 8, left, w });
  }

  // Position before paint to avoid a flash at (0,0).
  useLayoutEffect(() => {
    if (open) reposition();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      close();
    };
    const onReflow = () => reposition();
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onDown, true);
    window.addEventListener("resize", onReflow);
    window.addEventListener("scroll", onReflow, true);
    // move focus into the panel
    const id = requestAnimationFrame(() => {
      const first = panelRef.current?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      (first ?? panelRef.current)?.focus();
    });
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("resize", onReflow);
      window.removeEventListener("scroll", onReflow, true);
      cancelAnimationFrame(id);
      // return focus to the trigger when closing
      triggerRef.current?.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <>
      {trigger({
        ref: triggerRef,
        onClick: () => setOpen((v) => !v),
        "aria-expanded": open,
        "aria-haspopup": "dialog",
        "data-open": open,
      })}
      {open &&
        createPortal(
          <div
            ref={panelRef}
            role="dialog"
            aria-label={label}
            tabIndex={-1}
            style={{
              position: "fixed",
              top: pos.top,
              left: pos.left,
              width: pos.w,
              maxHeight: `calc(100vh - ${pos.top + 12}px)`,
              zIndex: 50,
              animation: "rise 0.16s var(--ease-out-quint) both",
            }}
            className="overflow-y-auto rounded-lg border border-border bg-surface p-4 shadow-[var(--shadow-lg)] outline-none"
          >
            {typeof children === "function" ? children(close) : children}
          </div>,
          document.body,
        )}
    </>
  );
}
