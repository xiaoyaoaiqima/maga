declare module 'd3-force-3d' {
  export interface ForceCollide<NodeDatum> {
    (alpha?: number): void;
    initialize(nodes: NodeDatum[]): void;
    radius(): (node: NodeDatum, i: number, nodes: NodeDatum[]) => number;
    radius(
      radius:
        | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number)
        | number,
    ): this;
    strength(): number;
    strength(strength: number): this;
    iterations(): number;
    iterations(iterations: number): this;
  }

  export function forceCollide<NodeDatum = any>(
    radius?:
      | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number)
      | number,
  ): ForceCollide<NodeDatum>;

  export function forceCenter(x?: number, y?: number, z?: number): any;

  export function forceLink<_NodeDatum = any, LinkDatum = any>(
    links?: LinkDatum[],
  ): any;

  export function forceManyBody(): any;

  export function forceRadial<NodeDatum = any>(
    radius:
      | ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number)
      | number,
    x?: number,
    y?: number,
    z?: number,
  ): any;

  export function forceSimulation<NodeDatum = any>(nodes?: NodeDatum[]): any;

  export function forceX<NodeDatum = any>(
    x?: ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number) | number,
  ): any;

  export function forceY<NodeDatum = any>(
    y?: ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number) | number,
  ): any;

  export function forceZ<NodeDatum = any>(
    z?: ((node: NodeDatum, i: number, nodes: NodeDatum[]) => number) | number,
  ): any;
}
