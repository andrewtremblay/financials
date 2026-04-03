// Core parsed data types

export interface FlowLine {
  source: string;
  amount: number | '*' | '?';
  target: string;
  color?: string;      // hex with optional .opacity
  opacity?: number;
}

export interface NodeDef {
  name: string;
  color?: string;
  opacity?: number;
}

export interface MoveDef {
  name: string;
  x: number;
  y: number;
}

export interface ParsedInput {
  flows: FlowLine[];
  nodeDefs: Map<string, NodeDef>;
  moves: MoveDef[];
  errors: string[];
}

// Settings types
export interface SkmSettings {
  size_w: number;
  size_h: number;
  margin_l: number;
  margin_r: number;
  margin_t: number;
  margin_b: number;
  bg_color: string;
  bg_transparent: boolean;
  node_w: number;
  node_h: number;
  node_spacing: number;
  node_border: number;
  node_theme: 'a' | 'b' | 'c' | 'd' | 'none';
  node_color: string;
  node_opacity: number;
  flow_curvature: number;
  flow_inheritfrom: 'source' | 'target' | 'outside-in' | 'none';
  flow_color: string;
  flow_opacity: number;
  layout_order: 'automatic' | 'exact';
  layout_justifyorigins: boolean;
  layout_justifyends: boolean;
  layout_reversegraph: boolean;
  layout_attachincompletesto: 'leading' | 'nearest' | 'trailing';
  labels_color: string;
  labels_hide: boolean;
  labels_highlight: number;
  labels_fontface: 'sans-serif' | 'serif' | 'monospace';
  labels_linespacing: number;
  labels_relativesize: number;
  labels_magnify: number;
  labelname_appears: boolean;
  labelname_size: number;
  labelname_weight: number;
  labelvalue_appears: boolean;
  labelvalue_fullprecision: boolean;
  labelvalue_position: 'above' | 'before' | 'after' | 'below';
  labelvalue_weight: number;
  labelposition_autoalign: number;
  labelposition_scheme: 'auto' | 'per_stage';
  labelposition_first: 'before' | 'after';
  labelposition_breakpoint: number;
  value_format: string;
  value_prefix: string;
  value_suffix: string;
  themeoffset_a: number;
  themeoffset_b: number;
  themeoffset_c: number;
  themeoffset_d: number;
  meta_mentionwebsite: boolean;
  meta_listimbalances: boolean;
  internal_iterations: number;
  internal_revealshadows: boolean;
}

// Sankey layout node (after d3-sankey computes positions)
export interface SankeyNode {
  id: string;
  name: string;
  x0?: number;
  x1?: number;
  y0?: number;
  y1?: number;
  value?: number;
  index?: number;
  depth?: number;
  height?: number;
  color: string;
  opacity: number;
  // d3-sankey adds sourceLinks / targetLinks
  sourceLinks?: SankeyLink[];
  targetLinks?: SankeyLink[];
}

export interface SankeyLink {
  source: SankeyNode | string;
  target: SankeyNode | string;
  value: number;
  color: string;
  opacity: number;
  width?: number;
  y0?: number;
  y1?: number;
  index?: number;
}
