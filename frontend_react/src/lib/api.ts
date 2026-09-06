import type {
  BudgetClassification,
  BudgetRule,
  BudgetType,
  CategoryOption,
  CategoryRule,
  MatchType,
  MonthData,
  MonthsResponse,
  NeedsReviewResponse,
  RangeData,
  RetirementModelsResponse,
  RetirementSettings,
  SectionOption,
  UntrackedIncomeBreakdown,
  UntrackedIncomeLabelStatus,
  UntrackedIncomeRule,
  UntrackedIncomeScope,
} from './budget-types';

// Matches budget_aggregate.VALID_RANGE_KEYS server-side. "1M" exists on the
// backend for symmetry/completeness but the frontend's range picker never
// requests it — a 1-month "range" is just single-month mode, already served
// by getMonth/getSankeymatic.
export type RangeKey = '1M' | '3M' | '6M' | '1Y' | 'YTD';

// Empty string in production (same-origin, FastAPI serves the built
// frontend directly). Set explicitly in .env.development for local dev
// against a separately-running `uvicorn api_server:app` process.
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new Error(`${resp.status} ${resp.statusText}${body ? `: ${body}` : ''}`);
  }
  return resp.json() as Promise<T>;
}

export function getMonths(): Promise<MonthsResponse> {
  return apiFetch('/api/months');
}

export function getMonth(yearMonth: string): Promise<MonthData> {
  return apiFetch(`/api/months/${encodeURIComponent(yearMonth)}`);
}

// Matches budget_sankeymatic.GROUP_BY_OPTIONS server-side. "section" (the
// original grouping, Budget -> expense Section -> line item) is the
// default; "classification" swaps the middle hub for Needs/Wants instead,
// mirroring the Budget Rules tab's 50/30/20 split (2026-08-02, user-requested).
export type SankeyGroupBy = 'section' | 'classification';

export function getSankeymatic(yearMonth: string, groupBy: SankeyGroupBy = 'section'): Promise<{ text: string }> {
  return apiFetch(`/api/months/${encodeURIComponent(yearMonth)}/sankeymatic?group_by=${groupBy}`);
}

// endYearMonth is the anchor month — the range runs backward from it (see
// budget_aggregate.compute_range_months for exactly how each range_key
// resolves to a concrete list of months).
export function getRange(rangeKey: RangeKey, endYearMonth: string): Promise<RangeData> {
  return apiFetch(`/api/range/${rangeKey}/${encodeURIComponent(endYearMonth)}`);
}

export function getRangeSankeymatic(
  rangeKey: RangeKey, endYearMonth: string, groupBy: SankeyGroupBy = 'section',
): Promise<{ text: string }> {
  return apiFetch(`/api/range/${rangeKey}/${encodeURIComponent(endYearMonth)}/sankeymatic?group_by=${groupBy}`);
}

export function getNeedsReview(yearMonth?: string): Promise<NeedsReviewResponse> {
  const qs = yearMonth ? `?year_month=${encodeURIComponent(yearMonth)}` : '';
  return apiFetch(`/api/needs-review${qs}`);
}

export function getCategories(): Promise<CategoryOption[]> {
  return apiFetch('/api/categories');
}

export function getSections(): Promise<SectionOption[]> {
  return apiFetch('/api/sections');
}

// A brand-new TOP-LEVEL section (Home, Daily Living, ... are the static
// ones) — distinct from createCategory below, which only adds a
// subcategory WITHIN an existing section.
export function createSection(label: string): Promise<SectionOption> {
  return apiFetch('/api/sections', {
    method: 'POST',
    body: JSON.stringify({ label }),
  });
}

export function createCategory(section: string, lineItem: string): Promise<CategoryOption> {
  return apiFetch('/api/categories', {
    method: 'POST',
    body: JSON.stringify({ section, line_item: lineItem }),
  });
}

export function setTransactionCategory(
  transactionId: string, category: string, note?: string | null,
): Promise<{ transaction_id: string; category: string }> {
  return apiFetch(`/api/transactions/${encodeURIComponent(transactionId)}/category`, {
    method: 'POST',
    body: JSON.stringify({ category, note: note ?? null }),
  });
}

// Edits the note on an already-ignored transaction without recategorizing —
// unlike setTransactionCategory above, this never triggers a plaid_sync
// resync server-side, so it's safe to call on every blur in the Ignored list.
export function updateIgnoreNote(transactionId: string, note: string): Promise<{ transaction_id: string; note: string }> {
  return apiFetch(`/api/transactions/${encodeURIComponent(transactionId)}/ignore-note`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
}

export function getCategoryRules(): Promise<CategoryRule[]> {
  return apiFetch('/api/category-rules');
}

export function createCategoryRule(
  pattern: string, matchType: MatchType, category: string, amount?: number | null,
): Promise<{ rule: CategoryRule; affected_transaction_count: number; affected_transaction_ids: string[] }> {
  return apiFetch('/api/category-rules', {
    method: 'POST',
    body: JSON.stringify({ pattern, match_type: matchType, category, amount: amount ?? null }),
  });
}

export function deleteCategoryRule(ruleId: string): Promise<{ removed: string }> {
  return apiFetch(`/api/category-rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
}

export function getBudgetRules(yearMonth: string): Promise<{ rules: BudgetRule[] }> {
  return apiFetch(`/api/months/${encodeURIComponent(yearMonth)}/budget-rules`);
}

export function getRangeBudgetRules(rangeKey: RangeKey, endYearMonth: string): Promise<{ rules: BudgetRule[] }> {
  return apiFetch(`/api/range/${rangeKey}/${encodeURIComponent(endYearMonth)}/budget-rules`);
}

export function getBudgetClassification(): Promise<BudgetClassification[]> {
  return apiFetch('/api/budget-classification');
}

export function setBudgetClassification(
  section: string, label: string, budgetType: BudgetType, housing: boolean, debt: boolean,
): Promise<BudgetClassification> {
  return apiFetch('/api/budget-classification', {
    method: 'POST',
    body: JSON.stringify({ section, label, budget_type: budgetType, housing, debt }),
  });
}

export function getUntrackedIncome(yearMonth: string): Promise<UntrackedIncomeBreakdown> {
  return apiFetch(`/api/months/${encodeURIComponent(yearMonth)}/untracked-income`);
}

export function getRangeUntrackedIncome(rangeKey: RangeKey, endYearMonth: string): Promise<UntrackedIncomeBreakdown> {
  return apiFetch(`/api/range/${rangeKey}/${encodeURIComponent(endYearMonth)}/untracked-income`);
}

export function getUntrackedIncomeLabels(yearMonth: string): Promise<UntrackedIncomeLabelStatus[]> {
  return apiFetch(`/api/untracked-income-labels?year_month=${encodeURIComponent(yearMonth)}`);
}

export function getUntrackedIncomeRules(): Promise<UntrackedIncomeRule[]> {
  return apiFetch('/api/untracked-income-rules');
}

export function createUntrackedIncomeRule(
  label: string, enabled: boolean, scope: UntrackedIncomeScope, yearMonth: string,
): Promise<UntrackedIncomeRule> {
  return apiFetch('/api/untracked-income-rules', {
    method: 'POST',
    body: JSON.stringify({ label, enabled, scope, year_month: yearMonth }),
  });
}

export function deleteUntrackedIncomeRule(ruleId: string): Promise<{ removed: string }> {
  return apiFetch(`/api/untracked-income-rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
}

export function getRetirementSettings(): Promise<RetirementSettings> {
  return apiFetch('/api/retirement/settings');
}

export function updateRetirementSettings(patch: Partial<RetirementSettings>): Promise<RetirementSettings> {
  return apiFetch('/api/retirement/settings', { method: 'POST', body: JSON.stringify(patch) });
}

export function getRetirementModels(): Promise<RetirementModelsResponse> {
  return apiFetch('/api/retirement/models');
}
