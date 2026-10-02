const ACTIONS = [
  ["Data", "Buka impor data", "M4 5h16v14H4z M8 9h8 M8 12h8 M8 15h5"],
  ["Analytics", "Buka analytics", "M4 19V11 M10 19V5 M16 19v-8 M22 19H2"],
  ["Journal", "Buka jurnal trade", "M6 3h12v18H6z M9 8h6 M9 12h6 M9 16h4"],
  ["Settings", "Pengaturan chart", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M19 5l-2 2 M7 17l-2 2"],
];

function RightToolbar({ onOpenData, onOpenAnalytics, onOpenJournal, onOpenSettings }) {
  const handlers = [onOpenData, onOpenAnalytics, onOpenJournal, onOpenSettings];

  return (
    <nav className="right-chart-toolbar" aria-label="Panel workspace">
      <span className="right-rail-spacer" />
      {ACTIONS.map(([label, title, path], index) => (
        <button key={label} type="button" className="right-tool-icon" title={title} aria-label={title} onClick={handlers[index]}>
          <svg className="right-tool-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path} /></svg>
          <small>{label}</small>
        </button>
      ))}
    </nav>
  );
}

export default RightToolbar;
