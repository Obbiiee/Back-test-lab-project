import { useEffect, useRef } from 'react';
export default function ReplayResetConfirmation({ onConfirm, onCancel }) {
  const dialog = useRef(null);
  useEffect(() => { const previous = document.activeElement; dialog.current?.querySelector('button')?.focus(); return () => { if (previous?.isConnected) previous.focus(); }; }, []);
  const keyDown = event => {
    if (event.key === 'Escape') { event.preventDefault(); onCancel(); }
    if (event.key === 'Tab') { event.preventDefault(); const buttons = [...dialog.current.querySelectorAll('button')], index = buttons.indexOf(document.activeElement); buttons[(index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length].focus(); }
  };
  return <div className="dialog-backdrop"><section ref={dialog} onKeyDown={keyDown} className="replay-date-dialog" role="alertdialog" aria-modal="true" aria-labelledby="reset-account-title" aria-describedby="reset-account-description">
    <header><strong id="reset-account-title">Reset paper account?</strong></header>
    <p id="reset-account-description">This clears pending orders, open positions, exit records and journal notes. Export your results from Analysis before continuing.</p>
    <div className="analysis-actions"><button onClick={onCancel}>Cancel reset</button><button className="place-order" onClick={onConfirm}>Confirm reset</button></div>
  </section></div>;
}
