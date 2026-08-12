import Phaser from "phaser";
import { SaveSystem } from "../game/systems/SaveSystem";
import { OverlayUi } from "../game/ui/OverlayUi";

interface ClientMessage {
  source?: string;
  type?: string;
  id?: number;
  method?: string;
  args?: unknown[];
  detail?: Record<string, unknown>;
}

interface PywebviewWindow extends Window {
  pywebview?: { api?: Record<string, (...args: unknown[]) => Promise<unknown>> };
}

const RPC_METHODS = new Set([
  "list_modalities", "defaults", "default_node_names", "pick_folder", "video_output",
  "pick_video_output", "reset_video_output", "save_pose_npz", "generate_demo",
  "scan_folder", "test_connect", "start", "poll", "stop",
]);

const STEP_NAMES: Record<number, string> = {
  1: "选择数据类型",
  2: "选择本地文件夹",
  3: "连接协调器",
  4: "训练与收获",
};

export class ClientGuide {
  private readonly shell = document.querySelector<HTMLElement>("#guide-shell");
  private readonly content = document.querySelector<HTMLElement>("#guide-content");
  private readonly progress = document.querySelector<HTMLElement>("#guide-progress");
  private iframe?: HTMLIFrameElement;
  private rewardAvailable = true;

  public constructor(private readonly game: Phaser.Game) {
    document.querySelector("#primary-action")?.addEventListener("click", () => this.open());
    document.querySelector("#guide-close")?.addEventListener("click", () => this.close());
    window.addEventListener("message", (event) => void this.handleMessage(event));
    window.addEventListener("pywebviewready", () => this.signalBridgeReady());
  }

  public start(): void {
    window.setTimeout(() => this.offerWelcome(), 950);
  }

  public open(): void {
    if (!this.shell || !this.content) return;
    if (!this.iframe) {
      this.iframe = document.createElement("iframe");
      this.iframe.title = "GBA-DF 机构创建向导";
      this.iframe.src = new URL("../client.html?embedded=1", window.location.href).href;
      this.iframe.addEventListener("load", () => this.signalBridgeReady());
      this.content.append(this.iframe);
    }
    this.shell.hidden = false;
  }

  public close(): void {
    if (this.shell) this.shell.hidden = true;
  }

  private offerWelcome(): void {
    try {
      if (localStorage.getItem("gba-df-client-welcome") === "seen") return;
      localStorage.setItem("gba-df-client-welcome", "seen");
    } catch { /* local file storage may be unavailable on a locked-down host */ }
    const ui = this.game.registry.get("overlayUi") as OverlayUi | undefined;
    ui?.showActivity(
      "NEW PARTNER",
      "在小镇建起你的机构",
      "向导会陪你选择数据类型和本地文件夹、连接受邀的协调器，并在机构自己的工坊里完成训练。",
      [
        { label: "开始创建", detail: "约 4 个步骤", value: "start" },
        { label: "先逛逛小镇", detail: "随时从右上角回来", value: "explore" },
      ],
      (choice) => { if (choice === "start") this.open(); },
    );
  }

  private async handleMessage(event: MessageEvent<ClientMessage>): Promise<void> {
    if (!this.iframe || event.source !== this.iframe.contentWindow || event.data?.source !== "gba-df-client") return;
    const message = event.data;
    if (message.type === "rpc" && typeof message.id === "number" && message.method) {
      await this.handleRpc(message.id, message.method, message.args ?? []);
      return;
    }
    if (message.type === "step") {
      const step = Number(message.detail?.step ?? 1);
      if (this.progress) this.progress.textContent = `${step} / 4 · ${STEP_NAMES[step] ?? "机构创建"}`;
    }
    if (message.type === "connection") this.updatePartnerStatus(message.detail);
    if (message.type === "run") this.updateRunStatus(message.detail);
  }

  private async handleRpc(id: number, method: string, args: unknown[]): Promise<void> {
    let result: unknown;
    let error = "";
    try {
      if (!RPC_METHODS.has(method)) throw new Error("unsupported client bridge method");
      const api = (window as PywebviewWindow).pywebview?.api;
      const call = api?.[method];
      if (!call) throw new Error("desktop bridge is not ready");
      result = await call(...args);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : String(caught);
    }
    this.iframe?.contentWindow?.postMessage({ source: "gba-df-town", type: "rpc-result", id, result, error }, "*");
  }

  private signalBridgeReady(): void {
    this.iframe?.contentWindow?.postMessage({ source: "gba-df-town", type: "bridge-ready" }, "*");
  }

  private updatePartnerStatus(detail?: Record<string, unknown>): void {
    const state = String(detail?.state ?? "off");
    const partner = document.querySelector("#partner-count");
    if (partner) partner.textContent = state === "off" ? "0" : "1";
  }

  private updateRunStatus(detail?: Record<string, unknown>): void {
    const state = detail?.state as Record<string, unknown> | undefined;
    const summary = detail?.summary as Record<string, unknown> | undefined;
    const round = Number(summary?.current_round ?? summary?.rounds_done ?? 0);
    const roundNode = document.querySelector("#round-count");
    if (roundNode) roundNode.textContent = String(round);
    if (state?.running) this.rewardAvailable = true;
    if (!state?.done || state?.error || !this.rewardAvailable) return;
    this.rewardAvailable = false;
    const save = this.game.registry.get("saveSystem") as SaveSystem | undefined;
    save?.award(60);
    const coinNode = document.querySelector("#coin-count");
    if (coinNode && save) coinNode.textContent = String(save.snapshot().coins);
    const action = document.querySelector<HTMLButtonElement>("#primary-action");
    if (action) action.textContent = "查看本次协作 · +60";
    this.game.scene.getScenes(true)[0]?.cameras.main.flash(450, 242, 196, 94);
  }
}
