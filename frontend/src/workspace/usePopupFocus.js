import { useEffect, useRef } from 'react';
// Non-modal panels retain chart access for price picking and replay research.
export default function usePopupFocus(onClose, modal = false, returnFocusRef) {
  const ref = useRef(null), close = useRef(onClose);
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = returnFocusRef?.current ?? document.activeElement, node = ref.current;
    node?.querySelector('button:not(:disabled),input:not(:disabled)')?.focus();
    const key = event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close.current(); }
      if (modal && event.key === 'Tab') {
        const items = [...node.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(item => item.getClientRects().length);
        if (!items.length) return;
        const index = items.indexOf(document.activeElement);
        if (index < 0 || (event.shiftKey && index === 0) || (!event.shiftKey && index === items.length - 1)) { event.preventDefault(); items[event.shiftKey ? items.length - 1 : 0].focus(); }
      }
    };
    node?.addEventListener('keydown', key);
    return () => { node?.removeEventListener('keydown', key); if (previous?.isConnected) previous.focus(); };
  }, [modal, returnFocusRef]);
  return ref;
}
