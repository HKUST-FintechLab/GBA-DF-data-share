import Phaser from "phaser";

export class Npc extends Phaser.GameObjects.Container {
  public readonly line: string;
  public readonly npcName: string;

  public constructor(scene: Phaser.Scene, x: number, y: number, name: string, line: string, texture: string) {
    super(scene, x, y);
    this.npcName = name;
    this.line = line;
    const shadow = scene.add.ellipse(0, 19, 34, 11, 0x163b2d, 0.28);
    const sprite = scene.add.sprite(0, 0, texture).setOrigin(0.5, 0.75).setScale(1.45);
    const label = scene.add.text(0, -39, name, {
      fontFamily: "monospace",
      fontSize: "10px",
      color: "#fff9d5",
      backgroundColor: "#15392dcc",
      padding: { x: 4, y: 2 },
    }).setOrigin(0.5);
    this.add([shadow, sprite, label]);
    scene.add.existing(this);
    this.setDepth(y);
    scene.tweens.add({ targets: sprite, y: -2, duration: 900, yoyo: true, repeat: -1, ease: "Sine.inOut" });
  }
}
