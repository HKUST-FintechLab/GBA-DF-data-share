import Phaser from "phaser";

export interface FederationStatus {
  nodes?: Array<{ node_id: string; name: string; samples: number }>;
  solo_sessions?: Array<{ nodes: Array<unknown>; rounds: number; global_eps: number }>;
  metrics?: Array<unknown>;
  global_eps?: number;
  epsilon_budget?: number;
  audit_len?: number;
  secure_aggregation?: boolean;
  pending_rounds?: Array<unknown>;
}

export class CoordinatorApi {
  private readonly keyStorage = "gba-df:operator-read-key";
  private timer?: number;
  private stopped = false;

  public constructor(private readonly game: Phaser.Game) {
    document.querySelector("#operator-key")?.addEventListener("click", () => this.requestKey());
  }

  public start(): void {
    void this.refresh();
    this.timer = window.setInterval(() => void this.refresh(), 6000);
    window.addEventListener("beforeunload", () => this.stop(), { once: true });
  }

  public stop(): void {
    this.stopped = true;
    if (this.timer) window.clearInterval(this.timer);
  }

  private async refresh(): Promise<void> {
    if (this.stopped) return;
    const key = sessionStorage.getItem(this.keyStorage) ?? "";
    const headers = key ? { "X-Fed-Key": key } : undefined;
    try {
      const response = await fetch("../status", { headers, cache: "no-store" });
      if (response.status === 401) {
        this.setKeyButton(true);
        this.setConnectionHint("输入只读查看钥匙后，小镇会显示协调器的实时状态");
        return;
      }
      if (!response.ok) throw new Error(`status ${response.status}`);
      const status = await response.json() as FederationStatus;
      this.setKeyButton(false);
      this.game.registry.set("federationStatus", status);
      this.game.events.emit("federation-status", status);
      this.renderHud(status);
    } catch {
      this.setConnectionHint("中央机房暂时离线，正在等待重新连接…");
    }
  }

  private renderHud(status: FederationStatus): void {
    const isolatedNodes = status.solo_sessions?.reduce((sum, room) => sum + room.nodes.length, 0) ?? 0;
    const isolatedRounds = status.solo_sessions?.reduce((sum, room) => sum + room.rounds, 0) ?? 0;
    const partners = status.nodes?.length || isolatedNodes;
    const rounds = status.metrics?.length || isolatedRounds;
    this.setText("#partner-count", partners);
    this.setText("#round-count", rounds);
    this.setConnectionHint(status.pending_rounds?.length
      ? `有 ${status.pending_rounds.length} 个轮次正在等待伙伴集合完成`
      : "点击地面移动 · 方向键 / WASD 移动 · 靠近建筑或 NPC 按 E 互动");
  }

  private requestKey(): void {
    const key = window.prompt("输入协调器的只读查看钥匙。它只保存在当前浏览器标签中。", "")?.trim();
    if (key === undefined) return;
    if (key) sessionStorage.setItem(this.keyStorage, key);
    else sessionStorage.removeItem(this.keyStorage);
    void this.refresh();
  }

  private setKeyButton(visible: boolean): void {
    const button = document.querySelector<HTMLButtonElement>("#operator-key");
    if (button) button.hidden = !visible;
  }

  private setConnectionHint(copy: string): void {
    const hint = document.querySelector<HTMLElement>("#game-hint");
    if (hint && !document.querySelector("#dialogue-panel:not([hidden])")) hint.textContent = copy;
  }

  private setText(selector: string, value: number): void {
    const element = document.querySelector(selector);
    if (element) element.textContent = String(value);
  }
}
