import Phaser from "phaser";
import type { RuntimeMode } from "../../runtime/mode";
import { Npc } from "../entities/Npc";
import { PlacedBuilding } from "../entities/PlacedBuilding";
import { Player, type MovementKeys } from "../entities/Player";
import { SaveSystem, type BuildingKind } from "../systems/SaveSystem";
import { NavigationController } from "../systems/NavigationController";
import { OverlayUi } from "../ui/OverlayUi";

interface SceneData {
  x?: number;
  y?: number;
}

interface TownInteraction {
  id: string;
  type: string;
  label: string;
  target?: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface TiledProperty {
  name: string;
  value: string;
}

const WORLD_WIDTH = 1536;
const WORLD_HEIGHT = 1024;

export class TownScene extends Phaser.Scene {
  private player!: Player;
  private cursors!: Phaser.Types.Input.Keyboard.CursorKeys;
  private wasd!: Record<"up" | "down" | "left" | "right", Phaser.Input.Keyboard.Key>;
  private interactKey!: Phaser.Input.Keyboard.Key;
  private interactions: TownInteraction[] = [];
  private npcs: Npc[] = [];
  private spawn: Phaser.Math.Vector2 = new Phaser.Math.Vector2(765, 760);
  private ui!: OverlayUi;
  private save!: SaveSystem;
  private navigation?: NavigationController;
  private collisionBounds: Phaser.Geom.Rectangle[] = [];

  public constructor(private readonly runtimeMode: RuntimeMode) {
    super("TownScene");
  }

  public init(data: SceneData): void {
    this.spawn = new Phaser.Math.Vector2(data.x ?? 765, data.y ?? 760);
  }

  public create(): void {
    this.ui = this.registry.get("overlayUi") as OverlayUi;
    this.save = this.registry.get("saveSystem") as SaveSystem;
    this.ui.hideActivity();
    this.ui.hideDialogue();

    this.add.image(0, 0, "town-map").setOrigin(0).setDepth(0);
    this.drawAtmosphere();
    this.player = new Player(this, this.spawn.x, this.spawn.y);
    this.physics.world.setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
    this.readTiledObjects();
    this.restoreBuildings();
    this.navigation = new NavigationController(this, this.player, {
      bounds: new Phaser.Geom.Rectangle(0, 0, WORLD_WIDTH, WORLD_HEIGHT),
      obstacles: this.collisionBounds,
      gridSize: 28,
      agentPadding: 18,
      canNavigate: () => !this.ui.isModalOpen(),
    });

    this.cameras.main.setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
    this.cameras.main.startFollow(this.player, true, 0.08, 0.08);
    this.cameras.main.setZoom(this.scale.width < 900 ? 1.05 : 1.18);

    this.cursors = this.input.keyboard!.createCursorKeys();
    this.wasd = this.input.keyboard!.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.W,
      down: Phaser.Input.Keyboard.KeyCodes.S,
      left: Phaser.Input.Keyboard.KeyCodes.A,
      right: Phaser.Input.Keyboard.KeyCodes.D,
    }) as typeof this.wasd;
    this.interactKey = this.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.E);
    this.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.ESC).on("down", () => {
      this.ui.hideActivity();
      this.ui.hideDialogue();
    });

    this.updateHud();
    document.querySelector("#loading-screen")?.classList.add("is-hidden");
    this.time.delayedCall(450, () => {
      this.ui.showDialogue(
        "向导小禾",
        this.runtimeMode === "client"
          ? "先逛逛小镇吧。准备好时，右上角的“创建我的机构”会带你完成连接、数据选择和训练。"
          : "中央机房展示全镇的协作进度。点击地面或使用键盘移动，靠近门口按 E 就能进入。",
      );
    });
  }

  public update(): void {
    const keys: MovementKeys = {
      up: { isDown: this.cursors.up.isDown || this.wasd.up.isDown },
      down: { isDown: this.cursors.down.isDown || this.wasd.down.isDown },
      left: { isDown: this.cursors.left.isDown || this.wasd.left.isDown },
      right: { isDown: this.cursors.right.isDown || this.wasd.right.isDown },
    };
    this.navigation?.update(keys, !this.ui.isModalOpen());
    this.player.setDepth(this.player.y);

    const npc = this.nearestNpc();
    const interaction = this.nearestInteraction();
    if (npc) {
      this.ui.setHint(`E · 和 ${npc.npcName} 对话`);
      if (Phaser.Input.Keyboard.JustDown(this.interactKey)) this.ui.showDialogue(npc.npcName, npc.line);
    } else if (interaction) {
      const verb = interaction.type === "plot" ? "在这里建造" : `进入${interaction.label}`;
      this.ui.setHint(`E · ${verb}`);
      if (Phaser.Input.Keyboard.JustDown(this.interactKey)) this.activate(interaction);
    } else {
      this.ui.setHint("点击地面移动 · 方向键 / WASD 移动 · 靠近建筑或 NPC 按 E 互动");
    }
  }

  private readTiledObjects(): void {
    const map = this.make.tilemap({ key: "town-objects" });
    const barriers = map.getObjectLayer("collisions")?.objects ?? [];
    for (const object of barriers) {
      const x = object.x ?? 0;
      const y = object.y ?? 0;
      const width = object.width ?? 1;
      const height = object.height ?? 1;
      this.collisionBounds.push(new Phaser.Geom.Rectangle(x, y, width, height));
      const barrier = this.add.rectangle(x + width / 2, y + height / 2, width, height, 0, 0);
      this.physics.add.existing(barrier, true);
      this.physics.add.collider(this.player, barrier);
    }

    const interactions = map.getObjectLayer("interactions")?.objects ?? [];
    this.interactions = interactions.map((object) => ({
      id: object.name,
      type: object.type,
      label: this.property(object.properties as TiledProperty[] | undefined, "label") ?? object.name,
      target: this.property(object.properties as TiledProperty[] | undefined, "target"),
      x: object.x ?? 0,
      y: object.y ?? 0,
      width: object.width ?? 1,
      height: object.height ?? 1,
    }));

    const npcObjects = map.getObjectLayer("npcs")?.objects ?? [];
    this.npcs = npcObjects.map((object) => {
      const line = this.property(object.properties as TiledProperty[] | undefined, "line") ?? "你好！";
      const texture = object.type === "privacy" ? "npc-privacy" : object.type === "builder" ? "npc-builder" : "npc-guide";
      return new Npc(this, object.x ?? 0, object.y ?? 0, object.name, line, texture);
    });
  }

  private restoreBuildings(): void {
    const state = this.save.snapshot();
    for (const [plotId, kind] of Object.entries(state.buildings)) {
      const plot = this.interactions.find((item) => item.id === plotId);
      if (plot) this.placeBuilding(plot, kind);
    }
  }

  private placeBuilding(plot: TownInteraction, kind: BuildingKind): void {
    const width = Math.min(214, plot.width * 1.08);
    const centerX = plot.x + plot.width / 2;
    const centerY = plot.y + plot.height / 2 + 12;
    new PlacedBuilding(this, centerX, centerY, kind, width);
    const footprint = new Phaser.Geom.Rectangle(
      plot.x + plot.width * 0.14,
      plot.y + plot.height * 0.38,
      plot.width * 0.72,
      plot.height * 0.48,
    );
    if (Phaser.Geom.Rectangle.Contains(footprint, this.player.x, this.player.y)) {
      this.player.setPosition(centerX, plot.y + plot.height + 30);
    }
    this.collisionBounds.push(footprint);
    this.navigation?.addObstacle(footprint);
    const barrier = this.add.rectangle(
      footprint.centerX,
      footprint.centerY,
      footprint.width,
      footprint.height,
      0,
      0,
    );
    this.physics.add.existing(barrier, true);
    this.physics.add.collider(this.player, barrier);
  }

  private activate(interaction: TownInteraction): void {
    if (interaction.type === "plot") {
      const existing = this.save.snapshot().buildings[interaction.id];
      if (existing) {
        this.ui.showDialogue("建造师芽芽", `${interaction.label}已经有一间精心布置的机构。它只保存在你的本地小镇存档中。`);
        return;
      }
      this.ui.showBuildPicker(interaction.label, (kind, price) => this.build(interaction, kind, price));
      return;
    }
    if (interaction.target) {
      this.save.visit(interaction.target);
      this.scene.start("InteriorScene", {
        room: interaction.target,
        label: interaction.label,
        returnX: this.player.x,
        returnY: this.player.y + 22,
      });
    }
  }

  private build(plot: TownInteraction, kind: BuildingKind, price: number): void {
    if (!this.save.build(plot.id, kind, price)) {
      this.ui.showDialogue("建造师芽芽", "小镇币还不够。完成一次受邀的数据协作后，就能获得新的建设奖励。");
      return;
    }
    this.placeBuilding(plot, kind);
    this.updateHud();
    this.ui.showDialogue("建造师芽芽", "完成啦！新机构已经加入你的地图，烟囱和门牌也都安置好了。");
    this.cameras.main.flash(300, 244, 210, 107);
  }

  private nearestInteraction(): TownInteraction | undefined {
    return this.interactions
      .map((item) => ({ item, distance: Phaser.Math.Distance.Between(this.player.x, this.player.y, item.x + item.width / 2, item.y + item.height / 2) }))
      .filter(({ distance }) => distance < 105)
      .sort((a, b) => a.distance - b.distance)[0]?.item;
  }

  private nearestNpc(): Npc | undefined {
    return this.npcs
      .map((npc) => ({ npc, distance: Phaser.Math.Distance.Between(this.player.x, this.player.y, npc.x, npc.y) }))
      .filter(({ distance }) => distance < 78)
      .sort((a, b) => a.distance - b.distance)[0]?.npc;
  }

  private updateHud(): void {
    const coin = document.querySelector("#coin-count");
    if (coin) coin.textContent = String(this.save.snapshot().coins);
  }

  private drawAtmosphere(): void {
    for (let index = 0; index < 7; index += 1) {
      const mote = this.add.circle(700 + index * 25, 570 + (index % 2) * 12, 3, 0x7bf5ec, 0.8).setDepth(12);
      this.tweens.add({ targets: mote, y: mote.y - 22, alpha: 0.15, duration: 1200 + index * 120, yoyo: true, repeat: -1 });
    }
  }

  private property(properties: TiledProperty[] | undefined, name: string): string | undefined {
    return properties?.find((property) => property.name === name)?.value;
  }
}
