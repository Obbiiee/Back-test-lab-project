import usePopupFocus from './usePopupFocus.js';
export default function WorkspaceModal({ label, onClose, children, returnFocusRef }) {
  const ref = usePopupFocus(onClose, true, returnFocusRef);
  return <div ref={ref} className="dialog-backdrop" role="dialog" aria-modal="true" aria-label={label}>{children}</div>;
}
