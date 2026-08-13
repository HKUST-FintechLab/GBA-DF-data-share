import Phaser from "phaser";

/** A camera-following, touch-sized action shown over the nearby world object. */
export class WorldActionButton extends Phaser.GameObjects.Container {
  public constructor(
    scene: Phaser.Scene,
    x: number,
    y: number,
    label: string,
    onActivate: () => void,
  ) {
    super(scene, x, y);

    const text = scene.add.text(0, -1, label, {
      fontFamily: "monospace",
      fontSize: "14px",
      fontStyle: "bold",
      color: "#fff8d6",
      align: "center",
    }).setOrigin(0.5);
    const width = Math.max(112, text.width + 30);
    const shadow = scene.add.rectangle(0, 4, width, 42, 0x0d211a, 0.72)
      .setStrokeStyle(2, 0x513e2d, 0.9);
    const background = scene.add.rectangle(0, 0, width, 42, 0x1f5947, 0.98)
      .setStrokeStyle(3, 0xf2c45e, 1);

    this.add([shadow, background, text]);
    this.setSize(width, 46).setDepth(20_000).setInteractive({ useHandCursor: true });
    this.on("pointerover", () => this.setScale(1.05));
    this.on("pointerout", () => this.setScale(1));
    this.on(
      "pointerdown",
      (_pointer: Phaser.Input.Pointer, _localX: number, _localY: number, event: Phaser.Types.Input.EventData) => {
        event.stopPropagation();
        onActivate();
      },
    );

    scene.add.existing(this);
    this.setScale(0.82).setAlpha(0);
    scene.tweens.add({ targets: this, scale: 1, alpha: 1, duration: 150, ease: "Back.out" });
  }
}
