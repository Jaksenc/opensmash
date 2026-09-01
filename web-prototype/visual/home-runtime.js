// Keep the visual runtime's DOM initialization order explicit. Because these
// are normal module dependencies, Vite can discover and fetch them in parallel.
import "./grid-replica.js";
import "./logo-stage.js";
import "./crt-viewport.js";
import "./game-launcher.js";
import "./site-hardware.js";
