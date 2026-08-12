import type { RuntimeMode } from "../../runtime/mode";

export type BuildingKind = "clinic" | "research" | "community" | "garden";

export interface TownSave {
  version: 1;
  coins: number;
  buildings: Record<string, BuildingKind>;
  visitedRooms: string[];
}

const DEFAULT_SAVE: TownSave = {
  version: 1,
  coins: 180,
  buildings: {},
  visitedRooms: [],
};

export class SaveSystem {
  private readonly key: string;
  private state: TownSave;

  public constructor(mode: RuntimeMode) {
    this.key = `gba-df-town:${mode}:v1`;
    this.state = this.read();
  }

  public snapshot(): TownSave {
    return {
      ...this.state,
      buildings: { ...this.state.buildings },
      visitedRooms: [...this.state.visitedRooms],
    };
  }

  public build(plotId: string, kind: BuildingKind, price: number): boolean {
    if (this.state.buildings[plotId] || this.state.coins < price) return false;
    this.state.buildings[plotId] = kind;
    this.state.coins -= price;
    this.write();
    return true;
  }

  public visit(room: string): void {
    if (this.state.visitedRooms.includes(room)) return;
    this.state.visitedRooms.push(room);
    this.write();
  }

  public award(amount: number): void {
    this.state.coins += Math.max(0, Math.round(amount));
    this.write();
  }

  private read(): TownSave {
    try {
      const parsed = JSON.parse(localStorage.getItem(this.key) ?? "null") as Partial<TownSave> | null;
      if (!parsed || parsed.version !== 1) return { ...DEFAULT_SAVE, buildings: {}, visitedRooms: [] };
      return {
        version: 1,
        coins: Number.isFinite(parsed.coins) ? Number(parsed.coins) : DEFAULT_SAVE.coins,
        buildings: parsed.buildings ?? {},
        visitedRooms: Array.isArray(parsed.visitedRooms) ? parsed.visitedRooms : [],
      };
    } catch {
      return { ...DEFAULT_SAVE, buildings: {}, visitedRooms: [] };
    }
  }

  private write(): void {
    localStorage.setItem(this.key, JSON.stringify(this.state));
  }
}
