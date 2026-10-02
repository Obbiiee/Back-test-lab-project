const DRAWING_TOOLS = [
  ["trendline", "／", "Trend Line"],
  ["ray", "↗", "Ray"],
  ["horizontal", "─", "Horizontal Line"],
  ["vertical", "│", "Vertical Line"],
  ["rectangle", "□", "Rectangle"],
  ["text", "T", "Text"],
];

function LeftToolbar({ activeTool, onSelect }) {
  function chooseTool(event, tool) {
    onSelect(tool);
    event.currentTarget.closest("details")?.removeAttribute("open");
  }

  return (
    <nav className="left-chart-toolbar" aria-label="Chart tools">
      <button type="button" className={`tool-icon ${activeTool === "cursor" ? "selected" : ""}`} title="Cursor" aria-label="Cursor" aria-pressed={activeTool === "cursor"} onClick={() => onSelect("cursor")}>↖</button>
      <button type="button" className={`tool-icon ${activeTool === "crosshair" ? "selected" : ""}`} title="Crosshair" aria-label="Crosshair" aria-pressed={activeTool === "crosshair"} onClick={() => onSelect("crosshair")}>⌖</button>
      <span className="tool-rail-divider" />
      <details className="tool-group">
        <summary className="tool-icon" title="Drawing tools" aria-label="Drawing tools">╱</summary>
        <div className="tool-popover">
          <strong>Drawing tools</strong>
          {DRAWING_TOOLS.map(([tool, icon, label]) => (
            <button key={tool} type="button" className={activeTool === tool ? "selected" : ""} onClick={(event) => chooseTool(event, tool)}><span>{icon}</span>{label}</button>
          ))}
        </div>
      </details>
      <details className="tool-group">
        <summary className={`tool-icon position-tool-icon ${["long-position", "short-position"].includes(activeTool) ? "selected" : ""}`} title="Prediction / measurement" aria-label="Prediction and measurement">↗</summary>
        <div className="tool-popover">
          <strong>Prediction / measurement</strong>
          <button type="button" className={activeTool === "long-position" ? "selected" : ""} onClick={(event) => chooseTool(event, "long-position")}><span>↗</span>Long Position</button>
          <button type="button" className={activeTool === "short-position" ? "selected" : ""} onClick={(event) => chooseTool(event, "short-position")}><span>↘</span>Short Position</button>
        </div>
      </details>
      <span className="tool-rail-divider" />
      <details className="tool-group">
        <summary className="tool-icon" title="More tools" aria-label="More tools">⋯</summary>
        <div className="tool-popover">
          <strong>More tools</strong>
          <button type="button" className={activeTool === "circle" ? "selected" : ""} onClick={(event) => chooseTool(event, "circle")}><span>○</span>Circle</button>
          <button type="button" className={activeTool === "price-range" ? "selected" : ""} onClick={(event) => chooseTool(event, "price-range")}><span>↔</span>Price range</button>
        </div>
      </details>
    </nav>
  );
}

export default LeftToolbar;
