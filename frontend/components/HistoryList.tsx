// frontend/components/HistoryList.tsx
import type { ExtractionResult } from "@/lib/types";

interface HistoryEntry {
  fileName: string;
  result: ExtractionResult;
}

interface HistoryListProps {
  entries: HistoryEntry[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

export default function HistoryList({ entries, selectedIndex, onSelect }: HistoryListProps) {
  return (
    <aside className="history-sidebar">
      <h2 className="history-title">Historial</h2>
      <ul className="history-list">
        {entries.map((entry, idx) => (
          <li key={idx}>
            <button
              type="button"
              className={idx === selectedIndex ? "history-item selected" : "history-item"}
              onClick={() => onSelect(idx)}
              aria-current={idx === selectedIndex ? "true" : undefined}
              title={entry.fileName}
            >
              <span
                className={`status-dot status-${entry.result.status}`}
                aria-hidden="true"
              />
              <span className="history-file-name">{entry.fileName}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
