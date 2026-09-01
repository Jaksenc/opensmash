export default function FlameAction({
  cellClassName = "",
  className = "",
  children,
  ...buttonProps
}) {
  return (
    <div className={`launch-flow-fire-cell flame-bridge-cell ${cellClassName}`.trim()}>
      <button className={`launch-flow-action ${className}`.trim()} {...buttonProps}>
        {children}
      </button>
    </div>
  );
}
