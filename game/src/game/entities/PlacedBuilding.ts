import Phaser from "phaser";
import type { BuildingKind } from "../systems/SaveSystem";

const PALETTE: Record<BuildingKind, { wall: number; roof: number; sign: string }> = {
  clinic: { wall: 0xf1dfb4, roof: 0xb84f43, sign: "✚" },
  research: { wall: 0xdbe2d5, roof: 0x3b718b, sign: "◇" },
  community: { wall: 0xf0d4a8, roof: 0x82568c, sign: "♥" },
  garden: { wall: 0xdbe5ad, roof: 0x4e8b59, sign: "✿" },
};

export class PlacedBuilding extends Phaser.GameObjects.Container {
  public constructor(scene: Phaser.Scene, x: number, y: number, kind: BuildingKind) {
    super(scene, x, y);
    const palette = PALETTE[kind];
    const shadow = scene.add.ellipse(0, 40, 128, 32, 0x173929, 0.25);
    const body = scene.add.rectangle(0, 5, 104, 76, palette.wall).setStrokeStyle(4, 0x5e4633);
    const roof = scene.add.triangle(0, -47, -66, 24, 0, -34, 66, 24, palette.roof).setStrokeStyle(4, 0x543c35);
    const door = scene.add.rectangle(0, 25, 22, 36, 0x315463).setStrokeStyle(3, 0x51372b);
    const sign = scene.add.text(0, -26, palette.sign, { fontFamily: "serif", fontSize: "20px", color: "#fff1b0" }).setOrigin(0.5);
    this.add([shadow, body, roof, door, sign]);
    scene.add.existing(this);
    this.setDepth(y);
    this.setScale(0.1);
    scene.tweens.add({ targets: this, scale: 1, duration: 450, ease: "Back.out" });
  }
}
