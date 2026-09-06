export interface Transaction {
  date: string | null;
  description: string;
  amount: number;
  account: string | null;
  transaction_id: string | null;
  category: string | null;
}

export interface LineItem {
  label: string;
  row: number;
  projected: number | null;
  actual: number;
  difference: number | null;
  is_fixed: boolean;
  is_copy_projected: boolean;
  transactions: Transaction[];
}

export type SectionKind = 'income_savings' | 'expense';

export interface BudgetSection {
  key: string;
  label: string;
  kind: SectionKind;
  line_items: LineItem[];
  other?: LineItem;
}

export interface NeedsReviewBucket {
  category: string;
  amount: number;
  count: number;
  transactions: Transaction[];
}

// A transaction in a SYSTEM-recognized transfer/payment category (self-
// transfers, credit card payments, Venmo payments, boilerplate noise) —
// excluded from every total like IgnoredTransaction, but automatic rather
// than user-driven. Same bucketed shape as NeedsReviewBucket (grouped by
// raw category) since it's rendered the same way.
export type HiddenBucket = NeedsReviewBucket;

// A transaction the user explicitly marked ignored (RecategorizeModal's
// "Ignore this transaction" action) — excluded from every section total and
// the Sankey diagram, surfaced here purely for observation/potential later
// re-categorization, alongside the reason the user gave.
export interface IgnoredTransaction extends Transaction {
  note: string | null;
}

export interface MonthTotals {
  income: number;
  savings: number;
  expense: number;
  net: number;
}

// Fields shared by both the single-month response (/api/months/{ym}) and
// the multi-month rolling-range response (/api/range/{key}/{ym}) — every
// consumer of a "budget view" (BudgetSection, BudgetLineItemRow,
// NotesDrawer, budget_sankeymatic's flows) only ever needs these, so
// BudgetDashboard can hold either type in one piece of state without a
// runtime branch except where it displays the identifying month(s) itself.
export interface BudgetView {
  sections: BudgetSection[];
  needs_review: NeedsReviewBucket[];
  ignored: IgnoredTransaction[];
  hidden: HiddenBucket[];
  has_sheet_tab: boolean;
  totals: MonthTotals;
}

export interface MonthData extends BudgetView {
  year_month: string;
}

// Same shape as MonthData, but summed across N consecutive months (see
// budget_aggregate.aggregate_range_json) — year_months is the ordered list
// of months that were actually summed (may be shorter than the nominal
// window, e.g. "6M" near the start of available history).
export interface RangeData extends BudgetView {
  year_months: string[];
}

export interface MonthSummary {
  year_month: string;
  label: string;
  has_sheet_tab: boolean;
}

export interface MonthsResponse {
  months: MonthSummary[];
  default_year_month: string;
}

export interface NeedsReviewTransaction extends Transaction {
  needs_review_category: string;
  year_month: string;
}

export interface NeedsReviewResponse {
  transactions: NeedsReviewTransaction[];
  count: number;
}

export interface CategoryOption {
  category: string;
  section: string;
  line_item: string;
}

// A section from budget_schema.BUDGET_SECTIONS, for the "add a new
// category" section picker in RecategorizeModal.
export interface SectionOption {
  key: string;
  label: string;
}

export type MatchType = 'substring' | 'exact' | 'regex';

export interface CategoryRule {
  id: string;
  match_type: MatchType;
  pattern: string;
  category: string;
  // Optional — additionally requires the transaction's own amount to match
  // (within a cent) before this rule applies. For a merchant whose
  // description alone is too generic (recurring peer-to-peer payments like
  // Venmo, where the description is just "Venmo" regardless of who's being
  // paid for what), but a specific recurring dollar amount does identify a
  // specific real bill (2026-08-02, user-specified).
  amount: number | null;
  created_at: string;
}

// The transaction (or needs-review row) a RecategorizeModal was opened for.
export interface RecategorizeTarget {
  transaction: Transaction | NeedsReviewTransaction;
  // Label shown in the modal for context, e.g. the line item or needs-review category.
  contextLabel: string;
}

// One segment of a budget rule (e.g. "Needs" within 50/30/20) — see
// budget_rules.py's Segment dataclass, which this mirrors exactly.
export interface RuleSegment {
  key: string;
  label: string;
  actual_amount: number;
  // null when income is $0 for the period (division by zero avoided
  // server-side rather than sent as Infinity/NaN).
  actual_pct: number | null;
  target_pct: number;
  on_target: boolean | null;
}

export interface BudgetRule {
  key: string;
  label: string;
  description: string;
  // Set only for rules with a known data-fidelity caveat (currently 28/36's
  // gross-vs-net-income approximation) — shown in the UI, not hidden.
  caveat: string | null;
  income: number;
  segments: RuleSegment[];
}

export type BudgetType = 'need' | 'want';

// One expense line item's Need/Want/Housing/Debt tag — see
// budget_classification.py. Housing/debt are independent of budget_type (a
// mortgage payment is Need + Housing + Debt all at once).
export interface BudgetClassification {
  section: string;
  label: string;
  budget_type: BudgetType;
  housing: boolean;
  debt: boolean;
}

// The dollar amounts behind the diagram's "Untracked Income" node for a
// given month/range — see untracked_income.py's breakdown_for_month.
export interface UntrackedIncomeBreakdown {
  total: number;
  breakdown: Record<string, number>;
}

// Matches untracked_income.py's VALID_SCOPES exactly.
export type UntrackedIncomeScope = 'current' | 'current_and_future' | 'all';

// One Savings line item's eligibility + resolved status for a specific
// anchor month — GET /api/untracked-income-labels?year_month=...'s shape.
export interface UntrackedIncomeLabelStatus {
  label: string;
  is_untracked: boolean;
  amount: number;
}

// A stored date-scoped override — see untracked_income.py's add_rule.
export interface UntrackedIncomeRule {
  id: string;
  label: string;
  enabled: boolean;
  scope: UntrackedIncomeScope;
  start_month: string | null;
  end_month: string | null;
  created_at: string;
}

// Matches retirement_settings.DEFAULT_SETTINGS exactly — the single shared
// plan every retirement_*.py model is computed from.
export interface RetirementSettings {
  current_age: number;
  retirement_age: number;
  life_expectancy_age: number;
  current_portfolio_balance: number;
  annual_savings: number;
  annual_return_pct: number;
  inflation_pct: number;
  bond_yield_pct: number;
  withdrawal_rate_pct: number;
  desired_annual_spending: number;
  lean_annual_spending: number;
  fat_annual_spending: number;
  barista_annual_spending_gap: number;
  social_security_annual: number;
  pension_annual: number;
  risk_aversion: number;
}

// One retirement_engine.MODELS entry, computed — `result` shape varies per
// model (each retirement_*.py function returns its own small result dict),
// rendered generically by RetirementModelCard rather than typed per-model.
export interface RetirementModelResult {
  key: string;
  label: string;
  category: string;
  description: string;
  caveat: string | null;
  result: Record<string, unknown>;
}

export interface RetirementModelsResponse {
  settings: RetirementSettings;
  models: RetirementModelResult[];
}
