import Phaser from "phaser";
import type { BuildingKind } from "../systems/SaveSystem";

const FRAME: Record<BuildingKind, number> = {
  clinic: 0,
  research: 1,
  community: 2,
  garden: 3,
};

export class PlacedBuilding extends Phaser.GameObjects.Container {
  public constructor(scene: Phaser.Scene, x: number, y: number, kind: BuildingKind, width: number) {
    super(scene, x, y);
    const shadow = scene.add.ellipse(0, 8, width * 0.78, width * 0.18, 0x173929, 0.24);
    const sprite = scene.add.sprite(0, 0, "building-atlas", FRAME[kind]);
    sprite.setDisplaySize(width, width * (512 / 768)).setOrigin(0.5, 0.82);
    this.add([shadow, sprite]);
    scene.add.existing(this);
    this.setDepth(y);
    this.setScale(0.08);
    scene.tweens.add({ targets: this, scale: 1, duration: 520, ease: "Back.out" });
  }
}
