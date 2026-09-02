import { existsSync } from "node:fs";
import path from "node:path";

export function resolveProjectPaths(appRoot) {
  const pipelineProjectRoot = path.resolve(appRoot, "..");
  const localEngineRoot = path.join(pipelineProjectRoot, "BattleShip", "web-dist");
  const workspaceRoot = existsSync(localEngineRoot)
    ? pipelineProjectRoot
    : path.resolve(pipelineProjectRoot, "..");

  return {
    pipelineProjectRoot,
    engineRoot: path.join(workspaceRoot, "BattleShip", "web-dist"),
    pipelineUiRoot: path.join(pipelineProjectRoot, "play", "ui"),
  };
}
