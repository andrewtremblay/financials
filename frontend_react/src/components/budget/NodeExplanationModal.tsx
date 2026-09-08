import React from 'react';
import type { NodeExplanation } from '../../lib/nodeExplanations';
import type { RangeMode } from './RangePicker';
import UntrackedIncomeDetail from './UntrackedIncomeDetail';

interface Props {
  explanation: NodeExplanation;
  // Only used for the "Untracked Income" node's interactive breakdown/edit
  // panel (see UntrackedIncomeDetail) — every other node's explanation is
  // static text and ignores these (2026-08-02, user-requested: "a
  // breakdown to explain the number ... as well as an option to
  // remove/change/add untracked income").
  yearMonth?: string;
  rangeMode?: RangeMode;
  onUntrackedIncomeChanged?: () => void;
  onClose: () => void;
}

const NodeExplanationModal: React.FC<Props> = ({ explanation, yearMonth, rangeMode, onUntrackedIncomeChanged, onClose }) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-[26rem] max-w-full max-h-[85vh] overflow-y-auto bg-gray-850 border border-gray-300 dark:border-gray-700 rounded-lg shadow-2xl p-4">
        <div className="flex items-start justify-between gap-3 mb-2">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{explanation.title}</h2>
          <button onClick={onClose} className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white text-lg leading-none flex-shrink-0">
            ×
          </button>
        </div>
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{explanation.body}</p>

        {explanation.title === 'Untracked Income' && yearMonth && rangeMode && (
          <UntrackedIncomeDetail yearMonth={yearMonth} rangeMode={rangeMode} onChanged={onUntrackedIncomeChanged} />
        )}

        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
};

export default NodeExplanationModal;
