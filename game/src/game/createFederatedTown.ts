import Phaser from "phaser";
import type { RuntimeMode } from "../runtime/mode";
import { BootScene } from "./scenes/BootScene";
import { TownScene } from "./scenes/TownScene";

export function createFederatedTown(parent: string, runtimeMode: RuntimeMode): Phaser.Game {
  return new Phaser.Game({
    // Canvas keeps the desktop-client build broadly compatible with WebKit/webview
    // hosts while preserving crisp pixel-art rendering.
    type: Phaser.CANVAS,
    parent,
    width: 1280,
    height: 720,
    backgroundColor: "#87c982",
    pixelArt: true,
    roundPixels: true,
    physics: {
      default: "arcade",
      arcade: { debug: false },
    },
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    scene: [new BootScene(runtimeMode), new TownScene(runtimeMode)],
  });
}
