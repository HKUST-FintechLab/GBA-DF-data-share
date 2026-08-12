import Phaser from "phaser";
import type { RuntimeMode } from "../../runtime/mode";
import { SaveSystem } from "../systems/SaveSystem";
import { OverlayUi } from "../ui/OverlayUi";

export class BootScene extends Phaser.Scene {
  public constructor(private readonly runtimeMode: RuntimeMode) {
    super("BootScene");
  }

  public preload(): void {
    this.load.image("town-map", "assets/town-map.png");
    this.load.spritesheet("building-atlas", "assets/building-atlas.png", {
      frameWidth: 768,
      frameHeight: 512,
    });
    this.load.tilemapTiledJSON("town-objects", "maps/town.json");
  }

  public create(): void {
    this.registry.set("runtimeMode", this.runtimeMode);
    this.registry.set("saveSystem", new SaveSystem(this.runtimeMode));
    this.registry.set("overlayUi", new OverlayUi());
    this.createActorTextures();
    this.scene.start("TownScene");
  }

  private createActorTextures(): void {
    const graphics = this.make.graphics({ x: 0, y: 0 }, false);
    const actor = (key: string, shirt: number, hair: number, facing: "down" | "up" | "left" | "right" = "down") => {
      graphics.clear();
      graphics.fillStyle(0x21372f, 0.28).fillEllipse(16, 29, 22, 7);
      graphics.fillStyle(0xf0bd83).fillRect(9, 7, 14, 12);
      graphics.fillStyle(hair).fillRect(8, 4, 16, facing === "up" ? 12 : 7);
      if (facing === "left") graphics.fillStyle(hair).fillRect(7, 7, 5, 11);
      if (facing === "right") graphics.fillStyle(hair).fillRect(20, 7, 5, 11);
      graphics.fillStyle(shirt).fillRect(8, 17, 16, 10);
      graphics.fillStyle(0x284d65).fillRect(9, 27, 6, 4).fillRect(18, 27, 6, 4);
      if (facing === "down") graphics.fillStyle(0x2f473e).fillRect(12, 11, 2, 2).fillRect(18, 11, 2, 2);
      graphics.generateTexture(key, 32, 32);
    };
    actor("player-down", 0x4d83a3, 0x4b3028, "down");
    actor("player-up", 0x4d83a3, 0x4b3028, "up");
    actor("player-left", 0x4d83a3, 0x4b3028, "left");
    actor("player-right", 0x4d83a3, 0x4b3028, "right");
    actor("npc-guide", 0xd69a4c, 0x70432b);
    actor("npc-privacy", 0x4e9b81, 0x34424b);
    actor("npc-builder", 0xa46d9e, 0x70492e);
    graphics.destroy();
  }
}
