export const FLOW_AUDIO_CROSSFADE_MS = 1200;
export const FLOW_MUSIC_MAX_VOLUME = 0.72;

function clampVolume(value) {
  return Math.max(0, Math.min(value, 1));
}

function setMediaVolume(media, value) {
  const volume = clampVolume(value);
  media.volume = volume;
  media.dataset.mixVolume = volume.toFixed(4);
}

export function transitionMediaVolume(
  media,
  targetVolume,
  { duration = FLOW_AUDIO_CROSSFADE_MS, onComplete } = {},
) {
  if (!media) return () => {};

  const startVolume = clampVolume(media.volume);
  const target = clampVolume(targetVolume);
  if (Math.abs(startVolume - target) < 0.0001 || duration <= 0) {
    setMediaVolume(media, target);
    onComplete?.();
    return () => {};
  }

  const startedAt = performance.now();
  let frame = 0;
  let cancelled = false;

  const update = (now) => {
    if (cancelled) return;
    const progress = Math.max(0, Math.min((now - startedAt) / duration, 1));
    const eased = (1 - Math.cos(Math.PI * progress)) / 2;
    setMediaVolume(media, startVolume + (target - startVolume) * eased);
    if (progress < 1) {
      frame = requestAnimationFrame(update);
      return;
    }
    onComplete?.();
  };

  frame = requestAnimationFrame(update);
  return () => {
    cancelled = true;
    cancelAnimationFrame(frame);
  };
}
