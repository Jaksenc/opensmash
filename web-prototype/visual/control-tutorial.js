export const CONTROL_TUTORIAL_STORAGE_KEY = "opensmash.controls-complete.v1";

export function shouldRequireControllerTutorial({ completed, mobileControls }) {
  return !completed && !mobileControls;
}

export function readControllerTutorialCompletion(storage) {
  return storage?.getItem(CONTROL_TUTORIAL_STORAGE_KEY) === "complete";
}

export function saveControllerTutorialCompletion(storage) {
  storage?.setItem(CONTROL_TUTORIAL_STORAGE_KEY, "complete");
}

export function clearControllerTutorialCompletion(storage) {
  storage?.removeItem(CONTROL_TUTORIAL_STORAGE_KEY);
}
