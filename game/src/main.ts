import "./styles.css";
import { createFederatedTown } from "./game/createFederatedTown";
import { getRuntimeMode } from "./runtime/mode";

const runtimeMode = getRuntimeMode();
document.documentElement.dataset.mode = runtimeMode;

const primaryAction = document.querySelector<HTMLButtonElement>("#primary-action");
if (primaryAction && runtimeMode === "client") {
  primaryAction.hidden = false;
}

createFederatedTown("game-root", runtimeMode);
