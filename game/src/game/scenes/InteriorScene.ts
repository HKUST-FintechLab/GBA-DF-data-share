import Phaser from "phaser";
import { Player, type MovementKeys } from "../entities/Player";
import { OverlayUi, type ActivityDetail } from "../ui/OverlayUi";
import type { FederationStatus } from "../../services/CoordinatorApi";
import { NavigationController } from "../systems/NavigationController";
import { WorldActionButton } from "../ui/WorldActionButton";

interface InteriorData {
  room?: string;
  label?: string;
  returnX?: number;
  returnY?: number;
}

interface Hotspot {
  x: number;
  y: number;
  label: string;
  copy: string;
  detail?: ActivityDetail;
}

const DATA_BOX_DETAIL: ActivityDetail = {
  eyebrow: "PRIVACY MODULE 01 · LOCAL ONLY",
  title: "本地数据箱：先把原始记录留在机构里",
  summary: "它负责把机构自己的录制文件转换成联邦训练可用、但仍留在本机的数值材料。整个准备过程发生在机构节点内。",
  steps: [
    { marker: "01", title: "读取本地记录", copy: "读取眼动 CSV、动作视频或姿态文件、EEG/fMRI 时序等机构文件。" },
    { marker: "02", title: "提取模态特征", copy: "在本机完成视频转姿态、时序统计和对应模态的特征工程。" },
    { marker: "03", title: "公共规则变换", copy: "使用固定的 public_scales 公共尺度归一化，不从参与者数据反推缩放参数。" },
    { marker: "04", title: "形成叶计数", copy: "进入数据无关的森林结构，每条记录在每棵树中只落入一个叶子并形成整数计数。" },
  ],
  resultLabel: "这一站产生什么？",
  result: "原始录制与逐条特征继续保存在机构节点；箱子只为下一站准备本地整数叶计数，此时尚未上传。",
  protections: ["原始记录留在本地", "本地特征提取", "固定公共归一化", "数据无关森林"],
};

const PRIVACY_MACHINE_DETAIL: ActivityDetail = {
  eyebrow: "PRIVACY MODULE 02 · MASKING",
  title: "隐私加工机：把本地计数变成可安全汇总的消息",
  summary: "它不会把逐条样本交给协调器，而是把整数叶计数绑定到本轮精确参与名单，再叠加节点之间可相互抵消的成对掩码。",
  steps: [
    { marker: "01", title: "绑定精确队伍", copy: "根据本轮全部节点的 node_id 与 X25519 公钥生成 cohort fingerprint，防止不同名单的消息被混合。" },
    { marker: "02", title: "限制单条贡献", copy: "每条记录在每棵树中只贡献一个叶子，因此该树叶计数向量的 L1 敏感度为 1。" },
    { marker: "03", title: "叠加成对掩码", copy: "节点两两协商掩码；同一对节点分别加上和减去同一个值，单个上传保持被遮蔽。" },
    { marker: "04", title: "签名封装", copy: "节点用本地 Ed25519 密钥签署受约束的 JSON 消息，并附上本轮名单指纹。" },
  ],
  resultLabel: "准备上传的内容",
  result: "带成对掩码的整数叶计数、节点签名和必要协议元数据；不包含原始录制或逐条特征行。",
  protections: ["精确队伍指纹", "X25519 成对掩码", "Ed25519 节点签名", "受约束 JSON"],
};

const FEDERATION_TOWER_DETAIL: ActivityDetail = {
  eyebrow: "PRIVACY MODULE 03 · FEDERATION",
  title: "联邦发送塔：只汇总全镇需要的共同结果",
  summary: "发送塔负责把已遮蔽的计数送入对应联邦轮次。协调器等待精确队伍到齐后恢复池化总和，再执行差分隐私与审计流程。",
  steps: [
    { marker: "01", title: "确认协调器与邀请", copy: "节点先核对邀请中的协调器密钥指纹，并以受邀机构身份加入对应轮次。" },
    { marker: "02", title: "收集完整队伍", copy: "只有 cohort fingerprint 完全一致且精确参与队伍到齐，掩码才会在池化总和中抵消。" },
    { marker: "03", title: "汇总后加入噪声", copy: "协调器只对恢复出的池化叶计数加入 Laplace 噪声，并通过持久化账本按轮扣除 epsilon。" },
    { marker: "04", title: "生成模型与审计", copy: "共同结果形成可下载的无 pickle JSON 模型，同时写入协调器签名、哈希链式审计记录。" },
  ],
  resultLabel: "网络里实际流动什么？",
  result: "节点发出带掩码的计数和协议元数据；完成后全镇获得共享模型、轮次指标与可验证审计记录。",
  protections: ["协调器指纹固定", "完整队伍汇总", "中央差分隐私", "epsilon 全局账本", "签名审计链"],
};

const ROOM_COPY: Record<string, { title: string; subtitle: string; accent: number }> = {
  "data-center": { title: "中央机房", subtitle: "全镇共同模型与协作看板", accent: 0x46ddd2 },
  clinic: { title: "安心诊所", subtitle: "机构的本地数据工坊", accent: 0xd7645d },
  community: { title: "伙伴之家", subtitle: "参与者交流与奖励空间", accent: 0xbd7dc0 },
  research: { title: "研究小屋", subtitle: "机构的本地研究与协作空间", accent: 0x4e9bbb },
  garden: { title: "数据花园", subtitle: "培育本地数据与共同模型的温室", accent: 0x58a66d },
  library: { title: "隐私图书馆", subtitle: "用小游戏认识每一道保护", accent: 0x60a5c5 },
  workshop: { title: "学习工坊", subtitle: "共同模型的成长实验室", accent: 0x62a86e },
  market: { title: "装扮市集", subtitle: "用小镇币布置机构和角色", accent: 0xe89c43 },
};

export class InteriorScene extends Phaser.Scene {
  private room = "data-center";
  private label = "中央机房";
  private returnPosition = new Phaser.Math.Vector2(765, 760);
  private player!: Player;
  private cursors!: Phaser.Types.Input.Keyboard.CursorKeys;
  private wasd!: Record<"up" | "down" | "left" | "right", Phaser.Input.Keyboard.Key>;
  private interactKey!: Phaser.Input.Keyboard.Key;
  private ui!: OverlayUi;
  private hotspots: Hotspot[] = [];
  private dashboardText?: Phaser.GameObjects.Text;
  private navigation!: NavigationController;
  private worldAction?: WorldActionButton;
  private worldActionKey = "";

  public constructor() {
    super("InteriorScene");
  }

  public init(data: InteriorData): void {
    this.room = data.room ?? "data-center";
    this.label = data.label ?? ROOM_COPY[this.room]?.title ?? "机构工坊";
    this.returnPosition = new Phaser.Math.Vector2(data.returnX ?? 765, data.returnY ?? 760);
  }

  public create(): void {
    document.documentElement.dataset.gameScene = "interior";
    this.ui = this.registry.get("overlayUi") as OverlayUi;
    this.ui.hideDialogue();
    this.drawRoom();
    this.player = new Player(this, 480, 535);
    this.physics.world.setBounds(70, 80, 820, 500);
    this.navigation = new NavigationController(this, this.player, {
      bounds: new Phaser.Geom.Rectangle(70, 80, 820, 500),
      gridSize: 26,
      agentPadding: 12,
      canNavigate: () => !this.ui.isModalOpen(),
    });
    this.cameras.main.setBounds(0, 0, 960, 640).centerOn(480, 320).setZoom(Math.min(this.scale.width / 960, this.scale.height / 640));

    this.cursors = this.input.keyboard!.createCursorKeys();
    this.wasd = this.input.keyboard!.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.W,
      down: Phaser.Input.Keyboard.KeyCodes.S,
      left: Phaser.Input.Keyboard.KeyCodes.A,
      right: Phaser.Input.Keyboard.KeyCodes.D,
    }) as typeof this.wasd;
    this.interactKey = this.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.E);
    this.input.keyboard!.addKey(Phaser.Input.Keyboard.KeyCodes.ESC).on("down", () => {
      if (this.ui.isModalOpen()) this.ui.hideActivity();
      else this.leave();
    });
    this.ui.showDialogue(this.label, ROOM_COPY[this.room]?.subtitle ?? "欢迎来到机构的数据工坊。");
    if (this.room === "data-center") {
      this.renderFederationStatus(this.registry.get("federationStatus") as FederationStatus | undefined);
      this.game.events.on("federation-status", this.renderFederationStatus, this);
      this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
        this.game.events.off("federation-status", this.renderFederationStatus, this);
      });
    }
  }

  public update(): void {
    const keys: MovementKeys = {
      up: { isDown: this.cursors.up.isDown || this.wasd.up.isDown },
      down: { isDown: this.cursors.down.isDown || this.wasd.down.isDown },
      left: { isDown: this.cursors.left.isDown || this.wasd.left.isDown },
      right: { isDown: this.cursors.right.isDown || this.wasd.right.isDown },
    };
    this.navigation.update(keys, !this.ui.isModalOpen());
    this.player.setDepth(this.player.y);

    if (this.ui.isModalOpen()) {
      this.hideWorldAction();
      return;
    }
    if (this.player.y > 550 && Math.abs(this.player.x - 480) < 70) {
      const activate = () => {
        this.navigation.cancel();
        this.leave();
      };
      this.showWorldAction("exit", 480, 525, "返回小镇", activate);
      this.ui.setHint("点击出口按钮，或按 E 返回小镇");
      if (Phaser.Input.Keyboard.JustDown(this.interactKey)) activate();
      return;
    }
    const hotspot = this.hotspots
      .map((item) => ({ item, distance: Phaser.Math.Distance.Between(this.player.x, this.player.y, item.x, item.y) }))
      .filter(({ distance }) => distance < 82)
      .sort((a, b) => a.distance - b.distance)[0]?.item;
    if (hotspot) {
      const activate = () => {
        this.navigation.cancel();
        if (hotspot.detail) this.ui.showDetail(hotspot.detail);
        else this.ui.showDialogue(hotspot.label, hotspot.copy);
      };
      this.showWorldAction(`hotspot:${hotspot.label}`, hotspot.x, hotspot.y - 62, `查看${hotspot.label}`, activate);
      this.ui.setHint(`点击设施按钮，或按 E 查看${hotspot.label}`);
      if (Phaser.Input.Keyboard.JustDown(this.interactKey)) activate();
    } else {
      this.hideWorldAction();
      this.ui.setHint("点击地面移动 · 方向键 / WASD 移动 · 靠近设施会出现互动按钮");
    }
  }

  private drawRoom(): void {
    const palette = ROOM_COPY[this.room] ?? { title: this.label, subtitle: "机构数据工坊", accent: 0x67b7a1 };
    const graphics = this.add.graphics();
    graphics.fillStyle(0x132a22).fillRect(0, 0, 960, 640);
    graphics.fillStyle(0xead7a3).fillRoundedRect(55, 65, 850, 535, 18);
    graphics.fillStyle(0x7d5b43).fillRect(75, 85, 810, 44);
    graphics.fillStyle(0xc99964).fillRect(75, 129, 810, 430);
    graphics.lineStyle(2, 0xb18457, 0.5);
    for (let x = 75; x <= 885; x += 48) graphics.lineBetween(x, 129, x, 559);
    for (let y = 129; y <= 559; y += 48) graphics.lineBetween(75, y, 885, y);
    graphics.fillStyle(0x345c4d).fillRect(418, 552, 124, 48);

    this.add.text(480, 105, palette.title, {
      fontFamily: "monospace",
      fontSize: "22px",
      color: "#fff4c5",
      fontStyle: "bold",
    }).setOrigin(0.5).setDepth(10);

    if (this.room === "market") this.drawMarket(palette.accent);
    else if (this.room === "library") this.drawLibrary(palette.accent);
    else if (this.room === "community") this.drawCommunity(palette.accent);
    else this.drawDataWorkshop(palette.accent);
  }

  private drawDataWorkshop(accent: number): void {
    this.drawStation(190, 290, 0x4a6a5f, "本地数据箱", "▥");
    this.drawStation(480, 290, accent, "隐私加工机", "✦");
    this.drawStation(770, 290, 0x486f91, "联邦发送塔", "⌁");
    this.hotspots = [
      { x: 190, y: 380, label: "本地数据箱", copy: "原始记录和逐条特征保存在这家机构的节点里，在推荐训练路径中不会上传到协调器。", detail: DATA_BOX_DETAIL },
      { x: 480, y: 380, label: "隐私加工机", copy: "机器先在本地提取特征并形成整数叶计数，再为安全聚合加上成对掩码。", detail: PRIVACY_MACHINE_DETAIL },
      { x: 770, y: 380, label: "联邦发送塔", copy: "发送塔交付的是带掩码的计数和协议元数据。协调器汇总后加入差分隐私噪声，生成全镇共享模型。", detail: FEDERATION_TOWER_DETAIL },
    ];
    this.add.text(480, 445, "本地箱子  →  隐私加工  →  安全聚合  →  共同模型", {
      fontFamily: "monospace", fontSize: "14px", color: "#29483b", backgroundColor: "#f5e8b9", padding: { x: 12, y: 8 },
    }).setOrigin(0.5).setDepth(5);
  }

  private renderFederationStatus(status?: FederationStatus): void {
    this.dashboardText?.destroy();
    const isolatedNodes = status?.solo_sessions?.reduce((sum, room) => sum + room.nodes.length, 0) ?? 0;
    const isolatedRounds = status?.solo_sessions?.reduce((sum, room) => sum + room.rounds, 0) ?? 0;
    const partners = status?.nodes?.length || isolatedNodes;
    const rounds = status?.metrics?.length || isolatedRounds;
    const budget = status?.epsilon_budget ?? 0;
    const spent = status?.global_eps ?? 0;
    const privacy = status ? (status.secure_aggregation ? "安全聚合" : "中央差分隐私演示") : "等待协调器状态";
    const copy = status
      ? `伙伴 ${partners}   ·   完成轮次 ${rounds}   ·   ε ${spent}/${budget}   ·   审计事件 ${status.audit_len ?? 0}   ·   ${privacy}`
      : "正在连接协调器…若启用了查看钥匙，请在小镇右上角输入。";
    this.dashboardText = this.add.text(480, 157, copy, {
      fontFamily: "monospace",
      fontSize: "12px",
      color: "#fff3bc",
      backgroundColor: "#173d34e8",
      padding: { x: 12, y: 8 },
      align: "center",
    }).setOrigin(0.5).setDepth(12);
  }

  private drawLibrary(accent: number): void {
    for (let index = 0; index < 4; index += 1) this.drawStation(185 + index * 195, 285, index === 1 ? accent : 0x587a68, ["留在本地", "成对掩码", "隐私预算", "审计足迹"][index], "▤");
    this.hotspots = [
      { x: 185, y: 380, label: "第一章 · 留在本地", copy: "从录制文件到特征提取都在参与机构的节点完成，原始记录由机构自己保管。" },
      { x: 380, y: 380, label: "第二章 · 成对掩码", copy: "至少三家互不串通的节点共同参与时，成对掩码让协调器只恢复池化总和。" },
      { x: 575, y: 380, label: "第三章 · 隐私预算", copy: "每轮训练从全局 epsilon 预算中扣除一次，废弃轮次不花费预算。" },
      { x: 770, y: 380, label: "第四章 · 审计足迹", copy: "签名哈希链和可导出的验证包，让小镇的重要事件能够被离线核验。" },
    ];
  }

  private drawCommunity(accent: number): void {
    this.drawStation(285, 300, accent, "伙伴留言板", "♥");
    this.drawStation(675, 300, 0xd39c4f, "协作奖励箱", "●");
    this.hotspots = [
      { x: 285, y: 390, label: "伙伴留言板", copy: "这里会展示已加入小镇的机构、正在准备的轮次，以及 NPC 给参与者的引导消息。" },
      { x: 675, y: 390, label: "协作奖励箱", copy: "完成真实训练贡献后，客户端会把新的小镇币与纪念装扮带回本地存档。" },
    ];
  }

  private drawMarket(accent: number): void {
    for (let index = 0; index < 3; index += 1) this.drawStation(260 + index * 220, 300, index === 1 ? accent : 0x6b8d74, ["家具", "角色装扮", "机构招牌"][index], ["⌂", "♟", "✦"][index]);
    this.hotspots = [
      { x: 260, y: 390, label: "家具货架", copy: "这里预留给桌椅、盆栽、服务器灯饰等可购买物品。" },
      { x: 480, y: 390, label: "角色装扮", copy: "共享贡献获得的小镇币可以用于购买帽子、外套和背包，不影响训练权限。" },
      { x: 700, y: 390, label: "机构招牌", copy: "为自己的机构挑选门牌、屋顶配色和庭院装饰，让地图上的伙伴一眼认出它。" },
    ];
  }

  private drawStation(x: number, y: number, color: number, label: string, symbol: string): void {
    this.add.ellipse(x, y + 62, 150, 34, 0x4b382b, 0.25).setDepth(y - 1);
    this.add.rectangle(x, y, 148, 128, 0x27483d).setStrokeStyle(5, 0x503c2e).setDepth(y);
    this.add.rectangle(x, y - 8, 112, 78, color).setStrokeStyle(3, 0xe7d498).setDepth(y + 1);
    this.add.text(x, y - 12, symbol, { fontFamily: "serif", fontSize: "32px", color: "#fff0ae" }).setOrigin(0.5).setDepth(y + 2);
    this.add.text(x, y + 76, label, { fontFamily: "monospace", fontSize: "12px", color: "#fff8d4", backgroundColor: "#24473bcc", padding: { x: 6, y: 3 } }).setOrigin(0.5).setDepth(y + 3);
  }

  private leave(): void {
    this.ui.hideDialogue();
    this.hideWorldAction();
    this.scene.start("TownScene", { x: this.returnPosition.x, y: this.returnPosition.y });
  }

  private showWorldAction(key: string, x: number, y: number, label: string, onActivate: () => void): void {
    if (this.worldActionKey === key && this.worldAction?.active) return;
    this.hideWorldAction();
    this.worldActionKey = key;
    this.worldAction = new WorldActionButton(this, x, y, label, onActivate);
  }

  private hideWorldAction(): void {
    this.worldAction?.destroy();
    this.worldAction = undefined;
    this.worldActionKey = "";
  }
}
