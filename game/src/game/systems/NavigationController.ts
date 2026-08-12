import Phaser from "phaser";
import { Player, type MovementKeys } from "../entities/Player";

interface NavigationOptions {
  bounds: Phaser.Geom.Rectangle;
  obstacles?: Phaser.Geom.Rectangle[];
  gridSize?: number;
  agentPadding?: number;
  canNavigate?: () => boolean;
}

interface GridCell {
  column: number;
  row: number;
}

const DIRECTIONS = [
  { column: 1, row: 0, cost: 1 }, { column: -1, row: 0, cost: 1 },
  { column: 0, row: 1, cost: 1 }, { column: 0, row: -1, cost: 1 },
  { column: 1, row: 1, cost: Math.SQRT2 }, { column: 1, row: -1, cost: Math.SQRT2 },
  { column: -1, row: 1, cost: Math.SQRT2 }, { column: -1, row: -1, cost: Math.SQRT2 },
];

export class NavigationController {
  private readonly gridSize: number;
  private readonly columns: number;
  private readonly rows: number;
  private readonly obstacles: Phaser.Geom.Rectangle[];
  private readonly pointerHandler: (pointer: Phaser.Input.Pointer) => void;
  private waypoints: Phaser.Math.Vector2[] = [];
  private marker?: Phaser.GameObjects.Arc;
  private blockedFrames = 0;

  public constructor(
    private readonly scene: Phaser.Scene,
    private readonly player: Player,
    private readonly options: NavigationOptions,
  ) {
    this.gridSize = options.gridSize ?? 28;
    this.columns = Math.ceil(options.bounds.width / this.gridSize);
    this.rows = Math.ceil(options.bounds.height / this.gridSize);
    const padding = options.agentPadding ?? 16;
    this.obstacles = (options.obstacles ?? []).map((source) => this.inflate(source, padding));
    this.pointerHandler = (pointer) => this.navigateToPointer(pointer);
    scene.input.on("pointerdown", this.pointerHandler);
    scene.events.once(Phaser.Scenes.Events.SHUTDOWN, () => this.destroy());
  }

  public addObstacle(source: Phaser.Geom.Rectangle): void {
    this.obstacles.push(this.inflate(source, this.options.agentPadding ?? 16));
  }

  public update(keys: MovementKeys, enabled: boolean): void {
    const keyboardActive = keys.up.isDown || keys.down.isDown || keys.left.isDown || keys.right.isDown;
    if (keyboardActive) {
      this.clearDestination();
      this.player.move(keys, enabled);
      return;
    }
    if (!enabled) {
      this.player.stopMoving();
      return;
    }
    const waypoint = this.waypoints[0];
    if (!waypoint) {
      this.player.stopMoving();
      return;
    }
    const distance = Phaser.Math.Distance.Between(this.player.x, this.player.y, waypoint.x, waypoint.y);
    if (distance < 11) {
      this.waypoints.shift();
      if (!this.waypoints.length) this.clearDestination();
      return;
    }
    const body = this.player.body as Phaser.Physics.Arcade.Body;
    this.blockedFrames = body.blocked.none ? 0 : this.blockedFrames + 1;
    if (this.blockedFrames > 8) {
      this.clearDestination();
      return;
    }
    this.player.moveDirection(waypoint.x - this.player.x, waypoint.y - this.player.y);
  }

  private navigateToPointer(pointer: Phaser.Input.Pointer): void {
    if (pointer.button !== 0 || this.options.canNavigate?.() === false) return;
    const point = pointer.positionToCamera(this.scene.cameras.main) as Phaser.Math.Vector2;
    const path = this.findPath(
      new Phaser.Math.Vector2(this.player.x, this.player.y),
      new Phaser.Math.Vector2(point.x, point.y),
    );
    if (!path.length) {
      this.clearDestination();
      return;
    }
    this.waypoints = path;
    this.blockedFrames = 0;
    this.showMarker(path[path.length - 1]);
  }

  private findPath(startPoint: Phaser.Math.Vector2, requestedPoint: Phaser.Math.Vector2): Phaser.Math.Vector2[] {
    const start = this.toCell(startPoint);
    const requested = this.toCell(requestedPoint);
    const candidates = this.destinationCandidates(requested);
    for (const destination of candidates) {
      const cells = this.aStar(start, destination);
      if (!cells.length) continue;
      return this.simplify(cells).map((cell) => this.toPoint(cell));
    }
    return [];
  }

  private destinationCandidates(requested: GridCell): GridCell[] {
    const candidates: GridCell[] = [];
    const maximumRadius = Math.max(this.columns, this.rows);
    for (let radius = 0; radius <= maximumRadius && candidates.length < 40; radius += 1) {
      for (let row = requested.row - radius; row <= requested.row + radius; row += 1) {
        for (let column = requested.column - radius; column <= requested.column + radius; column += 1) {
          if (radius && Math.abs(column - requested.column) !== radius && Math.abs(row - requested.row) !== radius) continue;
          const cell = { column, row };
          if (this.isWalkable(cell)) candidates.push(cell);
        }
      }
      if (candidates.length) break;
    }
    return candidates.sort((a, b) => this.heuristic(a, requested) - this.heuristic(b, requested));
  }

  private aStar(start: GridCell, destination: GridCell): GridCell[] {
    const startKey = this.key(start);
    const destinationKey = this.key(destination);
    const open = new Set<string>([startKey]);
    const cells = new Map<string, GridCell>([[startKey, start]]);
    const cameFrom = new Map<string, string>();
    const score = new Map<string, number>([[startKey, 0]]);
    const estimate = new Map<string, number>([[startKey, this.heuristic(start, destination)]]);

    while (open.size) {
      let currentKey = "";
      let currentEstimate = Number.POSITIVE_INFINITY;
      for (const candidate of open) {
        const value = estimate.get(candidate) ?? Number.POSITIVE_INFINITY;
        if (value < currentEstimate) {
          currentKey = candidate;
          currentEstimate = value;
        }
      }
      if (currentKey === destinationKey) return this.reconstruct(cameFrom, cells, currentKey);
      open.delete(currentKey);
      const current = cells.get(currentKey)!;
      for (const direction of DIRECTIONS) {
        const neighbor = { column: current.column + direction.column, row: current.row + direction.row };
        if (!this.isWalkable(neighbor) && this.key(neighbor) !== startKey) continue;
        if (direction.column && direction.row) {
          if (!this.isWalkable({ column: current.column + direction.column, row: current.row })
            || !this.isWalkable({ column: current.column, row: current.row + direction.row })) continue;
        }
        const neighborKey = this.key(neighbor);
        const tentative = (score.get(currentKey) ?? Number.POSITIVE_INFINITY) + direction.cost;
        if (tentative >= (score.get(neighborKey) ?? Number.POSITIVE_INFINITY)) continue;
        cameFrom.set(neighborKey, currentKey);
        cells.set(neighborKey, neighbor);
        score.set(neighborKey, tentative);
        estimate.set(neighborKey, tentative + this.heuristic(neighbor, destination));
        open.add(neighborKey);
      }
    }
    return [];
  }

  private reconstruct(cameFrom: Map<string, string>, cells: Map<string, GridCell>, currentKey: string): GridCell[] {
    const path: GridCell[] = [cells.get(currentKey)!];
    while (cameFrom.has(currentKey)) {
      currentKey = cameFrom.get(currentKey)!;
      path.unshift(cells.get(currentKey)!);
    }
    path.shift();
    return path;
  }

  private simplify(path: GridCell[]): GridCell[] {
    if (path.length < 3) return path;
    const result: GridCell[] = [];
    let previousDirection = "";
    for (let index = 0; index < path.length; index += 1) {
      const next = path[index + 1];
      if (!next) {
        result.push(path[index]);
        continue;
      }
      const direction = `${Math.sign(next.column - path[index].column)},${Math.sign(next.row - path[index].row)}`;
      if (index > 0 && direction !== previousDirection) result.push(path[index]);
      previousDirection = direction;
    }
    return result;
  }

  private isWalkable(cell: GridCell): boolean {
    if (cell.column < 0 || cell.row < 0 || cell.column >= this.columns || cell.row >= this.rows) return false;
    const point = this.toPoint(cell);
    return !this.obstacles.some((obstacle) => Phaser.Geom.Rectangle.Contains(obstacle, point.x, point.y));
  }

  private toCell(point: Phaser.Math.Vector2): GridCell {
    return {
      column: Phaser.Math.Clamp(Math.floor((point.x - this.options.bounds.x) / this.gridSize), 0, this.columns - 1),
      row: Phaser.Math.Clamp(Math.floor((point.y - this.options.bounds.y) / this.gridSize), 0, this.rows - 1),
    };
  }

  private toPoint(cell: GridCell): Phaser.Math.Vector2 {
    return new Phaser.Math.Vector2(
      this.options.bounds.x + cell.column * this.gridSize + this.gridSize / 2,
      this.options.bounds.y + cell.row * this.gridSize + this.gridSize / 2,
    );
  }

  private heuristic(left: GridCell, right: GridCell): number {
    return Math.hypot(left.column - right.column, left.row - right.row);
  }

  private key(cell: GridCell): string {
    return `${cell.column},${cell.row}`;
  }

  private inflate(source: Phaser.Geom.Rectangle, padding: number): Phaser.Geom.Rectangle {
    const rectangle = Phaser.Geom.Rectangle.Clone(source);
    return Phaser.Geom.Rectangle.Inflate(rectangle, padding, padding);
  }

  private showMarker(point: Phaser.Math.Vector2): void {
    this.marker?.destroy();
    this.marker = this.scene.add.circle(point.x, point.y, 11, 0xf8d46b, 0.2)
      .setStrokeStyle(3, 0xfff0a8, 0.95)
      .setDepth(point.y - 1);
    this.scene.tweens.add({ targets: this.marker, scale: 0.55, alpha: 0.55, duration: 520, yoyo: true, repeat: -1 });
  }

  private clearDestination(): void {
    this.waypoints = [];
    this.blockedFrames = 0;
    this.marker?.destroy();
    this.marker = undefined;
    this.player.stopMoving();
  }

  private destroy(): void {
    this.scene.input.off("pointerdown", this.pointerHandler);
    this.marker?.destroy();
  }
}
