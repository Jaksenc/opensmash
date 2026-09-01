# Portrait style references

These are the canonical, project-owned style references for portrait-tile
generation. They replace the vanilla Mario, Samus, and Link tile inputs that
were previously sent to the image model.

The sources are successful generated portraits for Blake Robbins, Kaisha Hom,
and Rohan Sahai. Each source was reduced to 48x45 with Lanczos sampling and
then enlarged to 384x360 with Lanczos sampling. That deliberately matches the
information level and preprocessing of the old vanilla tile references while
avoiding copyrighted character imagery.

Keep this set fixed unless a deliberate visual A/B test selects a replacement;
using newly generated full-resolution portraits directly causes recursive
style drift toward crisp modern illustration.
