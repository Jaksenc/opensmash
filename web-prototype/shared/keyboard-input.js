export function hasShortcutModifier(event) {
  return Boolean(event?.metaKey || event?.ctrlKey || event?.altKey);
}
