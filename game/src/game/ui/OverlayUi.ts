import type { BuildingKind } from "../systems/SaveSystem";

export interface ActivityAction {
  label: string;
  detail?: string;
  value: string;
}

export interface DetailStep {
  marker: string;
  title: string;
  copy: string;
}

export interface ActivityDetail {
  eyebrow: string;
  title: string;
  summary: string;
  steps: DetailStep[];
  resultLabel: string;
  result: string;
  protections: string[];
}

export class OverlayUi {
  private readonly hint = document.querySelector<HTMLElement>("#game-hint");
  private readonly dialogue = document.querySelector<HTMLElement>("#dialogue-panel");
  private readonly dialogueSpeaker = document.querySelector<HTMLElement>("#dialogue-speaker");
  private readonly dialogueText = document.querySelector<HTMLElement>("#dialogue-text");
  private readonly activity = document.querySelector<HTMLElement>("#activity-shell");
  private readonly activityEyebrow = document.querySelector<HTMLElement>("#activity-eyebrow");
  private readonly activityTitle = document.querySelector<HTMLElement>("#activity-title");
  private readonly activityCopy = document.querySelector<HTMLElement>("#activity-copy");
  private readonly activityActions = document.querySelector<HTMLElement>("#activity-actions");
  private readonly guide = document.querySelector<HTMLElement>("#guide-shell");

  public constructor() {
    document.querySelector("#dialogue-close")?.addEventListener("click", () => this.hideDialogue());
    document.querySelector("#activity-close")?.addEventListener("click", () => this.hideActivity());
  }

  public setHint(copy: string): void {
    if (this.hint) this.hint.textContent = copy;
  }

  public showDialogue(speaker: string, copy: string): void {
    if (!this.dialogue || !this.dialogueSpeaker || !this.dialogueText) return;
    this.dialogueSpeaker.textContent = speaker;
    this.dialogueText.textContent = copy;
    this.dialogue.hidden = false;
  }

  public hideDialogue(): void {
    if (this.dialogue) this.dialogue.hidden = true;
  }

  public showActivity(
    eyebrow: string,
    title: string,
    copy: string,
    actions: ActivityAction[],
    onSelect: (value: string) => void,
  ): void {
    if (!this.activity || !this.activityEyebrow || !this.activityTitle || !this.activityCopy || !this.activityActions) return;
    this.activity.classList.remove("is-detail");
    this.activityEyebrow.textContent = eyebrow;
    this.activityTitle.textContent = title;
    this.activityCopy.textContent = copy;
    this.activityActions.replaceChildren();
    for (const action of actions) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = action.label;
      if (action.detail) {
        const detail = document.createElement("small");
        detail.textContent = action.detail;
        button.append(detail);
      }
      button.addEventListener("click", () => {
        this.hideActivity();
        onSelect(action.value);
      });
      this.activityActions.append(button);
    }
    this.activity.hidden = false;
  }

  public showDetail(detail: ActivityDetail): void {
    if (!this.activity || !this.activityEyebrow || !this.activityTitle || !this.activityCopy || !this.activityActions) return;
    this.hideDialogue();
    this.activity.classList.add("is-detail");
    this.activityEyebrow.textContent = detail.eyebrow;
    this.activityTitle.textContent = detail.title;
    this.activityCopy.textContent = detail.summary;
    this.activityActions.replaceChildren();

    const flow = document.createElement("ol");
    flow.className = "privacy-flow";
    for (const step of detail.steps) {
      const item = document.createElement("li");
      item.className = "privacy-flow-step";
      const marker = document.createElement("span");
      marker.className = "privacy-flow-marker";
      marker.textContent = step.marker;
      const title = document.createElement("strong");
      title.textContent = step.title;
      const copy = document.createElement("p");
      copy.textContent = step.copy;
      item.append(marker, title, copy);
      flow.append(item);
    }

    const result = document.createElement("section");
    result.className = "privacy-result";
    const resultLabel = document.createElement("strong");
    resultLabel.textContent = detail.resultLabel;
    const resultCopy = document.createElement("p");
    resultCopy.textContent = detail.result;
    result.append(resultLabel, resultCopy);

    const protections = document.createElement("div");
    protections.className = "privacy-tags";
    protections.setAttribute("aria-label", "保护机制");
    for (const protection of detail.protections) {
      const tag = document.createElement("span");
      tag.textContent = protection;
      protections.append(tag);
    }
    this.activityActions.append(flow, result, protections);
    this.activity.hidden = false;
  }

  public hideActivity(): void {
    if (this.activity) {
      this.activity.hidden = true;
      this.activity.classList.remove("is-detail");
    }
  }

  public isModalOpen(): boolean {
    // Dialogue cards are notifications: the player can keep exploring while
    // reading them. Only full-screen activities and the client guide lock input.
    return Boolean((this.activity && !this.activity.hidden) || (this.guide && !this.guide.hidden));
  }

  public showBuildPicker(plotLabel: string, onSelect: (kind: BuildingKind, price: number) => void): void {
    const choices: Array<ActivityAction & { price: number }> = [
      { label: "暖心诊所", detail: "60 小镇币", value: "clinic", price: 60 },
      { label: "研究小屋", detail: "80 小镇币", value: "research", price: 80 },
      { label: "伙伴会馆", detail: "70 小镇币", value: "community", price: 70 },
      { label: "数据花园", detail: "45 小镇币", value: "garden", price: 45 },
    ];
    this.showActivity(
      "BUILD MODE",
      `在${plotLabel}建造`,
      "挑一间喜欢的建筑。布置会保存在这台设备上，下次回到小镇仍然可见。",
      choices,
      (value) => {
        const choice = choices.find((item) => item.value === value);
        if (choice) onSelect(choice.value as BuildingKind, choice.price);
      },
    );
  }
}
