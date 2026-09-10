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
    <ul className="history-list">
      {entries.map((entry, idx) => (
        <li key={idx}>
          <button
            type="button"
            className={idx === selectedIndex ? "history-item selected" : "history-item"}
            onClick={() => onSelect(idx)}
          >
            <span className={`status-dot status-${entry.result.status}`} />
            {entry.fileName}
          </button>
        </li>
      ))}
    </ul>
  );
}
