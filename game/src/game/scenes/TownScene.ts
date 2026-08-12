import Phaser from "phaser";
import type { RuntimeMode } from "../../runtime/mode";

const WORLD_WIDTH = 1920;
const WORLD_HEIGHT = 1080;

export class TownScene extends Phaser.Scene {
  private player!: Phaser.Physics.Arcade.Sprite;
  private cursors!: Phaser.Types.Input.Keyboard.CursorKeys;
  private wasd!: Record<"up" | "down" | "left" | "right", Phaser.Input.Keyboard.Key>;

  public constructor(private readonly runtimeMode: RuntimeMode) {
    super("TownScene");
  }

  public create(): void {
    this.createPlaceholderTextures();
    this.drawWorld();
    this.player = this.physics.add.sprite(940, 610, "player").setDepth(20);
    this.player.setCollideWorldBounds(true);
    this.physics.world.setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT);

    this.cameras.main.setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
    this.cameras.main.startFollow(this.player, true, 0.1, 0.1);
    this.cameras.main.setZoom(1.25);

    this.cursors = this.input.keyboard!.createCursorKeys();
    this.wasd = this.input.keyboard!.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.W,
      down: Phaser.Input.Keyboard.KeyCodes.S,
      left: Phaser.Input.Keyboard.KeyCodes.A,
      right: Phaser.Input.Keyboard.KeyCodes.D,
    }) as typeof this.wasd;

    this.add.text(940, 525, this.runtimeMode === "client" ? "机构创建广场" : "中央机房", {
      fontFamily: "monospace",
      fontSize: "18px",
      color: "#fff4c2",
      backgroundColor: "#234638cc",
      padding: { x: 10, y: 6 },
    }).setOrigin(0.5).setDepth(10);

    document.querySelector("#loading-screen")?.classList.add("is-hidden");
  }

  public update(): void {
    const speed = 190;
    let x = 0;
    let y = 0;
    if (this.cursors.left.isDown || this.wasd.left.isDown) x -= 1;
    if (this.cursors.right.isDown || this.wasd.right.isDown) x += 1;
    if (this.cursors.up.isDown || this.wasd.up.isDown) y -= 1;
    if (this.cursors.down.isDown || this.wasd.down.isDown) y += 1;
    const direction = new Phaser.Math.Vector2(x, y).normalize().scale(speed);
    this.player.setVelocity(direction.x, direction.y);
  }

  private createPlaceholderTextures(): void {
    const graphics = this.make.graphics({ x: 0, y: 0 }, false);
    graphics.fillStyle(0xf3c16b).fillRect(7, 4, 18, 25);
    graphics.fillStyle(0x5e3b2f).fillRect(8, 0, 16, 9);
    graphics.fillStyle(0x5278a3).fillRect(9, 14, 14, 10);
    graphics.generateTexture("player", 32, 32);
    graphics.destroy();
  }

  private drawWorld(): void {
    const world = this.add.graphics();
    world.fillStyle(0x82bf71).fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
    world.fillStyle(0x79b56b).fillRect(0, 0, WORLD_WIDTH, 180);
    world.fillStyle(0x83bdd1).fillRect(0, 230, WORLD_WIDTH, 120);
    world.fillStyle(0xf0d79e).fillRoundedRect(0, 350, WORLD_WIDTH, 84, 18);
    world.fillStyle(0xe6cb8c).fillRoundedRect(900, 350, 120, 730, 18);
    world.fillStyle(0x386a55).fillRoundedRect(770, 455, 380, 240, 24);
    world.fillStyle(0xd9a85e).fillRoundedRect(800, 485, 320, 180, 18);
    world.fillStyle(0x234638).fillTriangle(770, 505, 960, 395, 1150, 505);
    world.fillStyle(0xa0d78a);
    for (let x = 60; x < WORLD_WIDTH; x += 125) {
      world.fillCircle(x, 90 + ((x / 125) % 2) * 35, 33);
      world.fillStyle(0x4b8a58).fillCircle(x, 80 + ((x / 125) % 2) * 35, 27);
      world.fillStyle(0xa0d78a);
    }
  }
}
