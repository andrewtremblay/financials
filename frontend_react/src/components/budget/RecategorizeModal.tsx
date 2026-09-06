import React, { useEffect, useState } from 'react';
import type { CategoryOption, IgnoredTransaction, MatchType, NeedsReviewTransaction, SectionOption, Transaction } from '../../lib/budget-types';
import { createCategory, createCategoryRule, createSection, getCategories, getSections, setTransactionCategory } from '../../lib/api';

// The pseudo-category the "Ignore this transaction" action assigns — must
// match sheet_category_map.IGNORED_CATEGORY server-side exactly.
const IGNORED_CATEGORY = 'IGNORED';

// A value the real section <select> can never actually hold (section keys
// are always uppercase-derived, see api_server._derive_category_key) —
// selecting it reveals the "name a new section" input instead of picking
// an existing one (2026-08-02, user-requested: "I want to be able to
// create new sections, not just sub-sections").
const NEW_SECTION_SENTINEL = '__new_section__';

interface Props {
  transaction: Transaction | NeedsReviewTransaction | IgnoredTransaction;
  onClose: () => void;
  // Transaction ids that actually moved as a result of this save — just
  // the one transaction for "Just this transaction" scope, or every
  // matched id for a merchant-wide rule — so the caller can highlight
  // where they landed (2026-08-02, user-requested).
  onSaved: (affectedTransactionIds: string[]) => void;
}

// Mirrors api_server.py's _derive_category_key — client-side only for an
// instant preview of the key that'll be created; the server derives (and
// persists) the real value, so this never needs to match byte-for-byte.
const STOPWORDS = new Set(['the', 'a', 'an', 'of', 'for', 'in', 'on', 'and', 'or', 'to', 'with']);
function previewCategoryKey(lineItem: string): string {
  const words = (lineItem.match(/[A-Za-z]+/g) ?? []).filter(w => !STOPWORDS.has(w.toLowerCase()));
  return words.map(w => w.toUpperCase()).join(' ');
}

// /api/categories itself is sorted by category key (e.g. "MORTGAGE WARREN"),
// which has no relationship to where a category actually lives — the
// dropdown read as shuffled. Sort by section then subcategory instead so
// options group the way the "{section} → {line_item}" label already implies
// (2026-08-01, user-specified).
function compareCategoryOption(a: CategoryOption, b: CategoryOption): number {
  return a.section.localeCompare(b.section, undefined, { sensitivity: 'base' })
    || a.line_item.localeCompare(b.line_item, undefined, { sensitivity: 'base' });
}

const RecategorizeModal: React.FC<Props> = ({ transaction, onClose, onSaved }) => {
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [sections, setSections] = useState<SectionOption[]>([]);
  const [selected, setSelected] = useState<string>(transaction.category ?? '');
  const [useCustom, setUseCustom] = useState(false);
  const [newSection, setNewSection] = useState('');
  const [newSectionName, setNewSectionName] = useState('');
  const [newLineItem, setNewLineItem] = useState('');
  const [scope, setScope] = useState<'transaction' | 'merchant'>('transaction');
  const [matchType, setMatchType] = useState<MatchType>('substring');
  const [pattern, setPattern] = useState(transaction.description);
  const [amountEnabled, setAmountEnabled] = useState(false);
  const [amount, setAmount] = useState(String(transaction.amount));
  // Ignoring is always per-transaction (no merchant-rule/pattern scope) —
  // it's an observation-only action, not a spending category (2026-08-02,
  // user-specified). Pre-filled with the existing note (if any) so
  // reopening the modal on an already-ignored transaction lets you edit it.
  const [mode, setMode] = useState<'category' | 'ignore'>(transaction.category === IGNORED_CATEGORY ? 'ignore' : 'category');
  const [ignoreNote, setIgnoreNote] = useState('note' in transaction ? transaction.note ?? '' : '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCategories()
      .then(cats => setCategories([...cats].sort(compareCategoryOption)))
      .catch(() => {
        /* dropdown just stays empty; "add a new category" still works */
      });
    getSections()
      .then(setSections)
      .catch(() => {
        /* section picker just stays empty */
      });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (mode === 'ignore') {
        if (!transaction.transaction_id) throw new Error('This transaction has no ID to ignore.');
        await setTransactionCategory(transaction.transaction_id, IGNORED_CATEGORY, ignoreNote.trim() || null);
        onSaved([transaction.transaction_id]);
        onClose();
        return;
      }

      let category: string;
      if (useCustom) {
        let section = newSection;
        if (!section) throw new Error('Pick a section for the new category.');
        if (section === NEW_SECTION_SENTINEL) {
          if (!newSectionName.trim()) throw new Error('Name the new section.');
          const createdSection = await createSection(newSectionName.trim());
          section = createdSection.key;
          setSections(prev => [...prev, createdSection]);
        }
        if (!newLineItem.trim()) throw new Error('Name the new subcategory.');
        const created = await createCategory(section, newLineItem.trim());
        category = created.category;
        setCategories(prev => [...prev, created].sort(compareCategoryOption));
      } else {
        category = selected.trim().toUpperCase();
        if (!category) throw new Error('Pick a category.');
      }

      if (scope === 'transaction') {
        if (!transaction.transaction_id) throw new Error('This transaction has no ID to recategorize.');
        await setTransactionCategory(transaction.transaction_id, category);
        onSaved([transaction.transaction_id]);
      } else {
        if (!pattern.trim()) throw new Error('Enter a merchant pattern.');
        let ruleAmount: number | null = null;
        if (amountEnabled) {
          ruleAmount = Number(amount);
          if (!Number.isFinite(ruleAmount)) throw new Error('Enter a valid amount.');
        }
        const result = await createCategoryRule(pattern.trim(), matchType, category, ruleAmount);
        onSaved(result.affected_transaction_ids);
      }
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-[28rem] max-w-full bg-gray-850 border border-gray-300 dark:border-gray-700 rounded-lg shadow-2xl p-4">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Recategorize</h2>
        <p className="text-xs text-gray-500 mb-3">
          {transaction.date ?? '—'} · {transaction.description} ·{' '}
          {transaction.amount.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
        </p>

        <button
          onClick={() => setMode(m => (m === 'ignore' ? 'category' : 'ignore'))}
          className="text-xs text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 mb-3"
        >
          {mode === 'ignore' ? '← Pick a category instead' : 'Ignore this transaction instead'}
        </button>

        {mode === 'ignore' ? (
          <>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
              Why ignore this? (optional)
            </label>
            <textarea
              value={ignoreNote}
              onChange={e => setIgnoreNote(e.target.value)}
              placeholder="e.g. duplicate charge, already refunded, not a real expense"
              rows={3}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100 mb-3"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              Ignored transactions are excluded from every total and the money-flow diagram — they only show up in the
              Ignored list at the bottom of the sidebar, for observation.
            </p>
          </>
        ) : (
          <>
        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Category</label>
        {!useCustom ? (
          <select
            value={selected}
            onChange={e => setSelected(e.target.value)}
            className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100 mb-1"
          >
            <option value="">— select —</option>
            {categories.map(c => (
              <option key={c.category} value={c.category}>
                {c.section} → {c.line_item} ({c.category})
              </option>
            ))}
          </select>
        ) : (
          <div className="mb-1 flex flex-col gap-2">
            <select
              value={newSection}
              onChange={e => setNewSection(e.target.value)}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100"
            >
              <option value="">— section —</option>
              {sections.map(s => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
              <option value={NEW_SECTION_SENTINEL}>+ Create a new section</option>
            </select>
            {newSection === NEW_SECTION_SENTINEL && (
              <input
                value={newSectionName}
                onChange={e => setNewSectionName(e.target.value)}
                placeholder="New section name, e.g. Business Expenses"
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100"
              />
            )}
            <input
              value={newLineItem}
              onChange={e => setNewLineItem(e.target.value)}
              placeholder="Subcategory name, e.g. Concert Tickets"
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100"
            />
            {newLineItem.trim() && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                New category: <span className="font-mono">{previewCategoryKey(newLineItem) || '—'}</span>
              </p>
            )}
          </div>
        )}
        <button onClick={() => setUseCustom(v => !v)} className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 mb-3">
          {useCustom ? 'Pick from list instead' : 'Category not listed? Add a new one'}
        </button>

        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Apply to</label>
        <div className="flex flex-col gap-1.5 mb-3">
          <label className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
            <input type="radio" checked={scope === 'transaction'} onChange={() => setScope('transaction')} />
            Just this transaction
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
            <input type="radio" checked={scope === 'merchant'} onChange={() => setScope('merchant')} />
            All transactions matching a pattern
          </label>
        </div>

        {scope === 'merchant' && (
          <div className="mb-3 pl-6 flex flex-col gap-2">
            <input
              value={pattern}
              onChange={e => setPattern(e.target.value)}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100"
            />
            <select
              value={matchType}
              onChange={e => setMatchType(e.target.value as MatchType)}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100"
            >
              <option value="substring">contains (substring)</option>
              <option value="exact">exact match</option>
              <option value="regex">regex</option>
            </select>
            <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
              <input type="checkbox" checked={amountEnabled} onChange={e => setAmountEnabled(e.target.checked)} />
              Only when amount is exactly
            </label>
            {amountEnabled && (
              <input
                type="number"
                step="0.01"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100"
              />
            )}
          </div>
        )}
          </>
        )}

        {error && <p className="text-xs text-red-600 dark:text-red-400 mb-2">{error}</p>}

        <div className="flex justify-end gap-2 mt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default RecategorizeModal;
