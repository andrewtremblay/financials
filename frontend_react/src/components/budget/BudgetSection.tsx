import React, { useState } from 'react';
import type { BudgetSection as BudgetSectionType, LineItem } from '../../lib/budget-types';
import { diffColorClass } from '../../lib/budgetColor';
import BudgetLineItemRow from './BudgetLineItemRow';

const STORAGE_KEY = 'financials.collapsedSections';

function loadCollapsed(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveCollapsed(set: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    // localStorage unavailable (private browsing etc) — collapse state just won't persist.
  }
}

function fmt(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

interface Props {
  section: BudgetSectionType;
  onSelectLineItem: (item: LineItem) => void;
  expandedNodeIds: Set<string>;
  lineItemToNodeId: Map<LineItem, string>;
  onToggleExpand: (item: LineItem) => void;
}

const BudgetSection: React.FC<Props> = ({ section, onSelectLineItem, expandedNodeIds, lineItemToNodeId, onToggleExpand }) => {
  const [collapsedSet, setCollapsedSet] = useState<Set<string>>(loadCollapsed);
  const collapsed = collapsedSet.has(section.key);

  const toggle = () => {
    setCollapsedSet(prev => {
      const next = new Set(prev);
      if (next.has(section.key)) next.delete(section.key);
      else next.add(section.key);
      saveCollapsed(next);
      return next;
    });
  };

  const items = section.other ? [...section.line_items, section.other] : section.line_items;
  const sectionActual = items.reduce((sum, li) => sum + li.actual, 0);
  const sectionProjected = items.every(li => li.projected !== null)
    ? items.reduce((sum, li) => sum + (li.projected ?? 0), 0)
    : null;
  const sectionDifference = sectionProjected !== null ? sectionActual - sectionProjected : null;

  return (
    <div className="border-b border-gray-200 dark:border-gray-800">
      <button
        onClick={toggle}
        className="w-full grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-800/40 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-200 truncate">
          <span className={`inline-block transition-transform ${collapsed ? '' : 'rotate-90'}`}>›</span>
          {section.label}
        </span>
        <span className="text-gray-500 w-20 text-right text-xs tabular-nums">{sectionProjected !== null ? fmt(sectionProjected) : '—'}</span>
        <span className="text-gray-900 dark:text-gray-100 w-20 text-right text-xs tabular-nums">{fmt(sectionActual)}</span>
        <span className={`w-20 text-right text-xs tabular-nums ${diffColorClass(sectionDifference, section.kind)}`}>
          {sectionDifference !== null ? fmt(sectionDifference) : '—'}
        </span>
      </button>
      {!collapsed && (
        <div className="pb-2">
          {items.map(item => {
            const nodeId = lineItemToNodeId.get(item);
            return (
              <BudgetLineItemRow
                key={item.row}
                item={item}
                sectionKind={section.kind}
                onClick={() => onSelectLineItem(item)}
                expanded={nodeId !== undefined && expandedNodeIds.has(nodeId)}
                onToggleExpand={() => onToggleExpand(item)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};

export default BudgetSection;
