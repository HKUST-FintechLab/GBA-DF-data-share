import Phaser from "phaser";

export interface MovementKeys {
  up: { isDown: boolean };
  down: { isDown: boolean };
  left: { isDown: boolean };
  right: { isDown: boolean };
}

export class Player extends Phaser.Physics.Arcade.Sprite {
  private facing: "down" | "up" | "left" | "right" = "down";
  private readonly baseScale = 1.6;

  public constructor(scene: Phaser.Scene, x: number, y: number) {
    super(scene, x, y, "player-down");
    scene.add.existing(this);
    scene.physics.add.existing(this);
    this.setDepth(30).setCollideWorldBounds(true).setScale(this.baseScale);
    this.setSize(15, 12).setOffset(8.5, 18);
  }

  public move(keys: MovementKeys, enabled = true): void {
    if (!enabled) {
      this.setVelocity(0, 0);
      return;
    }
    let x = 0;
    let y = 0;
    if (keys.left.isDown) x -= 1;
    if (keys.right.isDown) x += 1;
    if (keys.up.isDown) y -= 1;
    if (keys.down.isDown) y += 1;

    this.moveDirection(x, y, enabled);
  }

  public moveDirection(x: number, y: number, enabled = true): void {
    if (!enabled) {
      this.stopMoving();
      return;
    }
    if (x || y) {
      if (Math.abs(x) > Math.abs(y)) this.facing = x < 0 ? "left" : "right";
      else this.facing = y < 0 ? "up" : "down";
      this.setTexture(`player-${this.facing}`);
      this.setScale(this.baseScale, this.baseScale * (1 + Math.sin(this.scene.time.now / 85) * 0.025));
    } else {
      this.setScale(this.baseScale);
    }
    const velocity = new Phaser.Math.Vector2(x, y).normalize().scale(175);
    this.setVelocity(velocity.x, velocity.y);
  }

  public stopMoving(): void {
    this.setVelocity(0, 0);
    this.setScale(this.baseScale);
  }
}
