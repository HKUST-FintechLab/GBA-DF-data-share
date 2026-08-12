import Phaser from "phaser";
import type { RuntimeMode } from "../../runtime/mode";

export class BootScene extends Phaser.Scene {
  public constructor(private readonly runtimeMode: RuntimeMode) {
    super("BootScene");
  }

  public create(): void {
    this.registry.set("runtimeMode", this.runtimeMode);
    this.scene.start("TownScene");
  }
}
