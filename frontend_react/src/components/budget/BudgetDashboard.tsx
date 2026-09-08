import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { BudgetView, IgnoredTransaction, LineItem, MonthData, MonthSummary, NeedsReviewTransaction, RangeData, Transaction } from '../../lib/budget-types';
import type { SkmSettings } from '../../types';
import { getMonth, getMonths, getRange, getRangeSankeymatic, getSankeymatic, type SankeyGroupBy } from '../../lib/api';
import { deleteQueryParam, getQueryParam, setQueryParam } from '../../lib/url';
import { parseInput } from '../../lib/parser';
import { DEFAULT_SETTINGS } from '../../lib/settings';
import { computeSankeySize } from '../../lib/sankeySize';
import { useTheme } from '../../lib/theme';
import { EXPANSION_SEPARATOR, expandSankeymaticText, isExpandable } from '../../lib/sankeyExpansion';
import { explainNode, type NodeExplanation } from '../../lib/nodeExplanations';
import MonthPicker from './MonthPicker';
import RangePicker, { RANGE_MODES, RANGE_STEP_MONTHS, type RangeMode } from './RangePicker';
import BudgetSection from './BudgetSection';
import HiddenTransactionsQueue from './HiddenTransactionsQueue';
import IgnoredSection from './IgnoredSection';
import NotesDrawer from './NotesDrawer';
import RecategorizeModal from './RecategorizeModal';
import NodeExplanationModal from './NodeExplanationModal';
import NeedsReviewQueue from './NeedsReviewQueue';
import SankeyDiagram from '../SankeyDiagram';
import ExportButtons from '../ExportButtons';
import Spinner from '../Spinner';

// DEFAULT_SETTINGS.labelvalue_fullprecision is true, which is fine for the
// Sankey Builder's hand-typed round numbers but shows raw floating-point
// drift (e.g. "15847.300000000003") once d3-sankey lays out real summed
// dollar amounts — round to 2 decimals for this dashboard specifically.
const BASE_SANKEY_SETTINGS = { ...DEFAULT_SETTINGS, labelvalue_fullprecision: false };

// Unlike the Sankey Builder tool — where bg_color/labels_color are the
// user's own explicit, exported choice, so they deliberately stay fixed
// regardless of app theme — this dashboard's diagram is just part of the
// app chrome, so it should follow the light/dark toggle like everything
// else (2026-08-01, user-reported: "sankey diagram must also respect dark
// mode... create a black background"). SankeyDiagram.tsx already derives
// each label's readability halo from bg_color, so flipping that one value
// carries labels_color's contrast fix along for free. flow_opacity is
// bumped too: the same ribbon alpha blended against black reads noticeably
// darker/muddier than against white, so dark mode needs more opacity to
// look equally vivid, not because the base hues themselves are wrong.
const DARK_SANKEY_OVERRIDES: Partial<SkmSettings> = {
  bg_color: '#0a0a0a',
  labels_color: '#f3f4f6',
  flow_opacity: 0.65,
};

function fmtMoney(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

// Mirrors budget_sankeymatic.py's node_name()/shared_labels exactly: a
// line-item label used by more than one EXPENSE section (e.g. "Other" under
// both Home and Daily Living) is disambiguated in the generated Sankeymatic
// text as "Label (Section)"; every other label — including all income and
// savings items, which the backend never disambiguates — keeps its plain
// label. Builds the reverse map (node id as it appears in the diagram ->
// LineItem) so a click on a Sankey node/label can resolve back to the exact
// LineItem the sidebar would have opened for the same thing. Hub/aggregate
// nodes with no matching entry (Budget, Savings, section headers,
// Overspending, Extra Savings, Pre-Tax Salary) simply have no map entry.
//
// Also builds the reverse mapping (LineItem -> nodeId) using the SAME
// disambiguation pass, for the expand/collapse toggle in the sidebar (see
// handleToggleExpand below) — it needs to know a clicked LineItem's node id
// to add/remove it from expandedNodeIds. Relies on LineItem object identity
// staying stable within one monthData snapshot (the sidebar list and this
// map are built from the very same section.line_items arrays).
function buildNodeMaps(monthData: BudgetView | null): {
  nodeIdToLineItem: Map<string, LineItem>;
  lineItemToNodeId: Map<LineItem, string>;
} {
  const nodeIdToLineItem = new Map<string, LineItem>();
  const lineItemToNodeId = new Map<LineItem, string>();
  if (!monthData) return { nodeIdToLineItem, lineItemToNodeId };

  const labelToSections = new Map<string, Set<string>>();
  for (const section of monthData.sections) {
    if (section.kind !== 'expense') continue;
    const items = section.other ? [...section.line_items, section.other] : section.line_items;
    for (const li of items) {
      if (li.actual <= 0) continue;
      if (!labelToSections.has(li.label)) labelToSections.set(li.label, new Set());
      labelToSections.get(li.label)!.add(section.label);
    }
  }
  const sharedLabels = new Set(
    [...labelToSections.entries()].filter(([, sections]) => sections.size > 1).map(([label]) => label),
  );

  for (const section of monthData.sections) {
    const items = section.other ? [...section.line_items, section.other] : section.line_items;
    for (const li of items) {
      if (li.actual <= 0) continue;
      const nodeId = section.kind === 'expense' && sharedLabels.has(li.label)
        ? `${li.label} (${section.label})`
        : li.label;
      if (!nodeIdToLineItem.has(nodeId)) nodeIdToLineItem.set(nodeId, li);
      lineItemToNodeId.set(li, nodeId);
    }
  }
  return { nodeIdToLineItem, lineItemToNodeId };
}

const BudgetDashboard: React.FC = () => {
  const { theme } = useTheme();
  const [months, setMonths] = useState<MonthSummary[]>([]);
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  // 'single' (the default/original behavior) drives GET /api/months/{ym};
  // any other mode drives GET /api/range/{key}/{ym} instead, with
  // selectedMonth as the range's anchor (its last/most-recent month) — see
  // RangePicker.tsx for the mode list and budget_aggregate.compute_range_months
  // for how a mode+anchor resolves to a concrete list of months server-side.
  const [rangeMode, setRangeMode] = useState<RangeMode>('single');
  const [monthData, setMonthData] = useState<MonthData | RangeData | null>(null);
  const [loading, setLoading] = useState(false);
  // Tracked separately from `loading` — getSankeymatic/getRangeSankeymatic
  // is a second, independent request fired alongside getMonth/getRange (see
  // loadData below), not gated on the same promise. Without its own flag,
  // `loading` could flip false the moment the (usually faster) sidebar data
  // arrives while the diagram's own fetch was still in flight, letting the
  // diagram panel fall through to its empty-state message for a beat before
  // the real flows showed up (2026-08-02, user-reported: "the screen
  // appears to have no data loaded for a long period of time before the
  // data snaps in").
  const [sankeyLoading, setSankeyLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [drawerLineItem, setDrawerLineItem] = useState<LineItem | null>(null);
  // Pre-selects NotesDrawer's category filter when opened from a
  // sub-category expansion node click (see handleSankeyNodeClick below) —
  // null for a normal sidebar-row open, which shows every transaction.
  const [drawerCategoryFilter, setDrawerCategoryFilter] = useState<string | null>(null);
  const openDrawer = useCallback((item: LineItem, categoryFilter: string | null = null) => {
    setDrawerLineItem(item);
    setDrawerCategoryFilter(categoryFilter);
  }, []);
  const closeDrawer = useCallback(() => {
    setDrawerLineItem(null);
    setDrawerCategoryFilter(null);
  }, []);
  const [recategorizing, setRecategorizing] = useState<Transaction | NeedsReviewTransaction | IgnoredTransaction | null>(null);
  // transaction_ids affected by the most recently saved recategorize
  // action — rendered grayed-out wherever they show up next, so a switched
  // category's new destination is obvious without hiding anything
  // (2026-08-02, user-requested). Overwritten (not accumulated) by each
  // new save; cleared implicitly whenever the set no longer matches
  // what's on screen (a month/range switch naturally makes stale ids
  // irrelevant, since they won't match anything in the new view).
  const [recentlyMovedIds, setRecentlyMovedIds] = useState<Set<string>>(new Set());
  // Diagram nodes with no real transactions behind them (Budget, Savings/
  // section hubs, Overspending/Underspending/Untracked Income, sub-category
  // expansion nodes) explain themselves here instead of opening the (empty)
  // transactions drawer (2026-08-01, user-requested).
  const [explainingNode, setExplainingNode] = useState<NodeExplanation | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const [sankeymaticText, setSankeymaticText] = useState('');
  const svgRef = useRef<SVGSVGElement>(null);

  // Which hub feeds the diagram's leaf nodes: "section" (Home, Daily
  // Living, ...) or "classification" (Needs/Wants, from budget_rules.py's
  // same Need/Want tagging as the Budget Rules tab) — an optional lens on
  // top of the same underlying data, not a different dataset (2026-08-02,
  // user-requested: "have these wants / needs / savings optionally
  // displayed on a sankeymatic"). Session-only (not URL/localStorage
  // persisted) — a lightweight view toggle, not a durable preference.
  const [sankeyGroupBy, setSankeyGroupBy] = useState<SankeyGroupBy>('section');

  // Measured size of the diagram panel (minus its own p-4 padding) — passed
  // into computeSankeySize as a floor so the diagram fills the space it's
  // given instead of leaving empty gutter around a smaller-than-panel
  // canvas (2026-08-01, user-specified). ResizeObserver rather than a
  // one-time measurement since the panel's size changes with the browser
  // window and whenever the sidebar's own width changes.
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelSize, setPanelSize] = useState<{ width: number; height: number } | null>(null);
  useEffect(() => {
    const el = panelRef.current;
    if (!el) return;
    const PANEL_PADDING = 32; // p-4 on both axes (16px * 2)
    const measure = () => setPanelSize({
      width: Math.max(0, el.clientWidth - PANEL_PADDING),
      height: Math.max(0, el.clientHeight - PANEL_PADDING),
    });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Initial load: months list, then default to the last complete month
  // (server-computed) unless the URL already names a valid one. Also reads
  // ?range= so a shared/bookmarked range-mode URL restores exactly.
  //
  // Always writes ?month= back out here (even when it's just the
  // server-computed default, not something the user picked) — a range is
  // anchored on this month, so a range URL needs it pinned to stay
  // deterministic. Without this, sharing a link built from the default
  // anchor (never having touched the month picker) would omit ?month=
  // entirely, and reopening it later — once "last complete month" has
  // rolled over to a new month — would silently show a different range.
  useEffect(() => {
    getMonths()
      .then(d => {
        setMonths(d.months);
        const fromUrl = getQueryParam('month');
        const valid = fromUrl && d.months.some(m => m.year_month === fromUrl);
        const resolvedMonth = valid ? fromUrl! : d.default_year_month;
        setSelectedMonth(resolvedMonth);
        setQueryParam('month', resolvedMonth);

        const rangeFromUrl = getQueryParam('range');
        if (rangeFromUrl && (RANGE_MODES as string[]).includes(rangeFromUrl)) {
          setRangeMode(rangeFromUrl as RangeMode);
        }
      })
      .catch(e => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const loadData = useCallback((ym: string, mode: RangeMode, groupBy: SankeyGroupBy) => {
    setLoading(true);
    setSankeyLoading(true);
    setError(null);
    const dataPromise = mode === 'single' ? getMonth(ym) : getRange(mode, ym);
    dataPromise
      .then(setMonthData)
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
    const sankeyPromise = mode === 'single' ? getSankeymatic(ym, groupBy) : getRangeSankeymatic(mode, ym, groupBy);
    sankeyPromise
      .then(d => setSankeymaticText(d.text))
      .catch(() => setSankeymaticText(''))
      .finally(() => setSankeyLoading(false));
  }, []);

  useEffect(() => {
    if (selectedMonth) loadData(selectedMonth, rangeMode, sankeyGroupBy);
  }, [selectedMonth, rangeMode, sankeyGroupBy, refreshKey, loadData]);

  const handleMonthChange = (ym: string) => {
    setSelectedMonth(ym);
    setQueryParam('month', ym);
  };

  const handleRangeModeChange = (mode: RangeMode) => {
    setRangeMode(mode);
    if (mode === 'single') deleteQueryParam('range');
    else setQueryParam('range', mode);
  };

  const { nodeIdToLineItem, lineItemToNodeId } = React.useMemo(() => buildNodeMaps(monthData), [monthData]);

  // Which line items are drilled down into their underlying raw categories
  // as separate diagram nodes (2026-08-01, user-specified: "Savings > Other
  // has sub-subsections, I want to see the sub-subsections as nodes").
  // Opt-OUT, not opt-in: every expandable line item (isExpandable) starts
  // expanded by default (2026-08-02, user-specified: "I want these sub
  // subsections to start expanded") — collapsedNodeIds tracks only the ones
  // a user has explicitly collapsed back down, so the common case (nothing
  // in this set) needs zero special-casing to mean "everything expanded".
  // Keyed by node id, not by LineItem/month, so — like the left sidebar's
  // own section-collapse state — a preference set on one month naturally
  // carries over to the next rather than resetting on every switch;
  // expandSankeymaticText silently ignores any id that no longer resolves
  // to anything in the current month.
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<Set<string>>(new Set());
  const handleToggleExpand = useCallback((item: LineItem) => {
    const nodeId = lineItemToNodeId.get(item);
    if (!nodeId) return;
    setCollapsedNodeIds(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId); else next.add(nodeId);
      return next;
    });
  }, [lineItemToNodeId]);

  const expandedNodeIds = React.useMemo(() => {
    const ids = new Set<string>();
    for (const [nodeId, item] of nodeIdToLineItem) {
      if (isExpandable(item) && !collapsedNodeIds.has(nodeId)) ids.add(nodeId);
    }
    return ids;
  }, [nodeIdToLineItem, collapsedNodeIds]);

  const expandedSankeymaticText = React.useMemo(
    () => expandSankeymaticText(sankeymaticText, nodeIdToLineItem, expandedNodeIds),
    [sankeymaticText, nodeIdToLineItem, expandedNodeIds],
  );
  const parsedSankey = React.useMemo(() => parseInput(expandedSankeymaticText), [expandedSankeymaticText]);
  const sankeySettings = React.useMemo(
    () => ({
      ...BASE_SANKEY_SETTINGS,
      ...(theme === 'dark' ? DARK_SANKEY_OVERRIDES : {}),
      ...computeSankeySize(parsedSankey.parsed.flows, panelSize ?? undefined),
    }),
    [parsedSankey.parsed.flows, theme, panelSize],
  );

  const handleRecategorized = (affectedTransactionIds: string[] = []) => {
    setRecentlyMovedIds(new Set(affectedTransactionIds));
    setRefreshKey(k => k + 1);
  };

  const sectionLabels = React.useMemo(
    () => new Set((monthData?.sections ?? []).map(s => s.label)),
    [monthData],
  );
  const handleSankeyNodeClick = useCallback((nodeId: string) => {
    const item = nodeIdToLineItem.get(nodeId);
    if (item) {
      openDrawer(item);
      return;
    }
    // A sub-category expansion node ("{Parent} — {Category}", see
    // sankeyExpansion.ts) isn't itself a real LineItem, but its parent is —
    // open the SAME drawer the parent's own node would, pre-filtered to
    // this one category, instead of a separate static explanation modal
    // (2026-08-02, user-requested: "show the same sidebar as the parent...
    // only ... filtered").
    const sepIndex = nodeId.indexOf(EXPANSION_SEPARATOR);
    if (sepIndex !== -1) {
      const parentId = nodeId.slice(0, sepIndex);
      const category = nodeId.slice(sepIndex + EXPANSION_SEPARATOR.length);
      const parentItem = nodeIdToLineItem.get(parentId);
      if (parentItem) {
        openDrawer(parentItem, category);
        return;
      }
    }
    const explanation = explainNode(nodeId, sectionLabels);
    if (explanation) setExplainingNode(explanation);
  }, [nodeIdToLineItem, sectionLabels, openDrawer]);

  // Single-month mode: the anchor month's own label ("Jul 2026"). Range
  // mode: "<first month's label> – <last month's label>" derived from the
  // range response's actual year_months (which may be a shorter window
  // than the mode's nominal width near the start of available history, or
  // just one month for "YTD" in January) — not from the mode/anchor alone,
  // so the header always reflects exactly what was summed.
  const currentLabel = React.useMemo(() => {
    if (!selectedMonth) return undefined;
    if (rangeMode === 'single' || !monthData || !('year_months' in monthData)) {
      return months.find(m => m.year_month === selectedMonth)?.label;
    }
    const ymList = monthData.year_months;
    if (ymList.length === 0) return undefined;
    const labelFor = (ym: string) => months.find(m => m.year_month === ym)?.label ?? ym;
    return ymList.length === 1 ? labelFor(ymList[0]) : `${labelFor(ymList[0])} – ${labelFor(ymList[ymList.length - 1])}`;
  }, [selectedMonth, rangeMode, monthData, months]);

  // True from mount until getMonths() resolves and picks an initial month —
  // before that, `loading`/`sankeyLoading` are still false (loadData hasn't
  // even been called yet), which is exactly the gap that read as "no data,
  // nothing indicating why" on first paint.
  const pageLoading = !selectedMonth && !error;
  const showSidebarLoading = loading || pageLoading;
  const showDiagramLoading = sankeyLoading || pageLoading;

  return (
    <div className="flex h-full">
      {/* Left: sections */}
      <div className="w-[36rem] flex-shrink-0 flex flex-col border-r border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-sm font-bold text-gray-900 dark:text-white">Budget Dashboard</h1>
            {monthData && (
              <p className="text-xs text-gray-500 mt-0.5 truncate">
                Net {fmtMoney(monthData.totals.net)} · Income {fmtMoney(monthData.totals.income)} · Expenses {fmtMoney(monthData.totals.expense)}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Deliberately stays scoped to the anchor month even in range
                mode, not the whole range — recategorization is a per-
                transaction action and /api/needs-review has no range variant;
                extending it was out of scope for the range feature itself. */}
            <NeedsReviewQueue yearMonth={selectedMonth ?? undefined} refreshKey={refreshKey} onRecategorized={handleRecategorized} />
            {monthData && (
              <HiddenTransactionsQueue
                buckets={monthData.hidden}
                recentlyMovedIds={recentlyMovedIds}
                onRecategorize={t => setRecategorizing(t)}
              />
            )}
          </div>
        </div>
        <div className="flex-shrink-0 px-4 py-2 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-3 flex-wrap">
          {months.length > 0 && selectedMonth ? (
            <MonthPicker
              months={months}
              selected={selectedMonth}
              onChange={handleMonthChange}
              step={RANGE_STEP_MONTHS[rangeMode]}
            />
          ) : (
            // Skeleton placeholder matching MonthPicker's rough footprint —
            // without this the whole row is empty on first paint, then the
            // real picker pops in with no transition once months arrives.
            !error && <div className="h-6 w-40 rounded bg-gray-200 dark:bg-gray-800 animate-pulse" />
          )}
          <RangePicker mode={rangeMode} onChange={handleRangeModeChange} />
        </div>

        <div className="flex-1 overflow-y-auto">
          {showSidebarLoading && <Spinner label="Loading budget data…" className="py-16" />}
          {error && <p className="px-4 py-6 text-sm text-red-600 dark:text-red-400">{error}</p>}
          {monthData && !loading && (
            <>
              <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-gray-600 grid grid-cols-[1fr_auto_auto_auto] gap-3">
                <span />
                <span className="w-20 text-right">Projected</span>
                <span className="w-20 text-right">Actual</span>
                <span className="w-20 text-right">Diff</span>
              </div>
              {monthData.sections.map(section => (
                <BudgetSection
                  key={section.key}
                  section={section}
                  onSelectLineItem={openDrawer}
                  expandedNodeIds={expandedNodeIds}
                  lineItemToNodeId={lineItemToNodeId}
                  onToggleExpand={handleToggleExpand}
                />
              ))}
              <IgnoredSection transactions={monthData.ignored} onRecategorize={t => setRecategorizing(t)} />
            </>
          )}
        </div>
      </div>

      {/* Right: Sankey diagram, auto-updates with the selected month */}
      <div className="flex-1 flex flex-col overflow-hidden bg-gray-50 dark:bg-gray-950">
        <div className="flex-shrink-0 flex items-center justify-between gap-4 px-4 py-2 border-b border-gray-200 dark:border-gray-800 text-xs text-gray-500">
          <span>{currentLabel ? `${currentLabel} money flow` : 'Money flow'}</span>
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="flex items-center rounded border border-gray-300 dark:border-gray-700 overflow-hidden" role="group" aria-label="Group diagram by">
              {(['section', 'classification'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setSankeyGroupBy(mode)}
                  aria-pressed={sankeyGroupBy === mode}
                  className={`px-2 py-1 text-xs transition-colors ${
                    sankeyGroupBy === mode
                      ? 'bg-indigo-600 text-white'
                      : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  {mode === 'section' ? 'By Section' : 'By Need/Want'}
                </button>
              ))}
            </div>
            {parsedSankey.parsed.flows.length > 0 && (
              <div className="w-60 flex-shrink-0">
                <ExportButtons svgRef={svgRef} settings={sankeySettings} flowsText={expandedSankeymaticText} />
              </div>
            )}
          </div>
        </div>
        <div ref={panelRef} className="flex-1 min-h-0 p-4 overflow-auto">
          {showDiagramLoading ? (
            // A fetch is in flight — distinct from "confirmed no data below"
            // (previously both read as the same "No flow data" message,
            // which looked like an empty month rather than a page still
            // loading — 2026-08-02 fix).
            <Spinner label="Loading diagram…" className="h-full" />
          ) : parsedSankey.parsed.flows.length > 0 ? (
            <div className="inline-block shadow-xl rounded-sm overflow-hidden bg-white dark:bg-[#0a0a0a]">
              <SankeyDiagram
                flows={parsedSankey.parsed.flows}
                nodeDefs={parsedSankey.parsed.nodeDefs}
                settings={sankeySettings}
                svgRef={svgRef}
                scrollable
                zoomable
                onNodeClick={handleSankeyNodeClick}
              />
            </div>
          ) : (
            <p className="text-sm text-gray-600 p-6">No flow data for this {rangeMode === 'single' ? 'month' : 'period'}.</p>
          )}
        </div>
      </div>

      {drawerLineItem && (
        <NotesDrawer
          // Forces a fresh mount (and therefore a fresh categoryFilter
          // default) whenever the drawer switches to a different line item
          // or a different pre-selected category, rather than reusing the
          // same instance's stale filter state across an in-place prop
          // update (2026-08-02).
          key={`${drawerLineItem.label}-${drawerCategoryFilter ?? 'all'}`}
          title={drawerLineItem.label}
          subtitle={`Actual ${fmtMoney(drawerLineItem.actual)}${drawerLineItem.projected !== null ? ` · Projected ${fmtMoney(drawerLineItem.projected)}` : ''}`}
          transactions={drawerLineItem.transactions}
          initialCategoryFilter={drawerCategoryFilter}
          recentlyMovedIds={recentlyMovedIds}
          emptyExplanation={
            drawerLineItem.is_fixed
              ? 'This is a fixed estimate, not derived from transactions — there\'s no reliable way to identify it from Plaid data, so the amount is set manually.'
              : drawerLineItem.is_copy_projected
                ? 'No Plaid transaction data exists for this line (e.g. a payroll deduction that never touches a tracked account) — its Actual value mirrors whatever Projected is set to.'
                : undefined
          }
          onClose={closeDrawer}
          onRecategorize={t => setRecategorizing(t)}
        />
      )}
      {recategorizing && <RecategorizeModal transaction={recategorizing} onClose={() => setRecategorizing(null)} onSaved={handleRecategorized} />}
      {explainingNode && (
        <NodeExplanationModal
          explanation={explainingNode}
          yearMonth={selectedMonth ?? undefined}
          rangeMode={rangeMode}
          onUntrackedIncomeChanged={handleRecategorized}
          onClose={() => setExplainingNode(null)}
        />
      )}
    </div>
  );
};

export default BudgetDashboard;
