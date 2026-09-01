export default function RetroChoiceGrid({
  className = "",
  disabled = false,
  name,
  onChange,
  options,
  value,
}) {
  return (
    <div className={`boot-mode-grid ${className}`.trim()}>
      {options.map((option) => (
        <label
          className={`advanced-cell-frame flame-bridge-cell ${value === option.value ? "is-selected" : ""}`}
          key={option.value}
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
          />
          <span className="boot-mode-copy">
            <strong>{option.label}</strong>
            <small>{option.description}</small>
          </span>
        </label>
      ))}
    </div>
  );
}
