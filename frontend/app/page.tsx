// frontend/app/page.tsx
"use client";

import { useState } from "react";
import UploadForm from "@/components/UploadForm";
import ResultView from "@/components/ResultView";
import HistoryList from "@/components/HistoryList";
import type { ExtractionResult } from "@/lib/types";

interface HistoryEntry {
  fileName: string;
  result: ExtractionResult;
}

export default function Home() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  function handleResult(result: ExtractionResult, fileName: string) {
    setHistory((prev) => [{ fileName, result }, ...prev]);
    setSelectedIndex(0);
  }

  function handleSelect(index: number) {
    setSelectedIndex(index);
  }

  return (
    <main className="page">
      <h1>Extractor de Facturas ARCA</h1>
      <UploadForm onResult={handleResult} />

      <div className="layout">
        {history.length > 0 && (
          <HistoryList entries={history} selectedIndex={selectedIndex} onSelect={handleSelect} />
        )}
        {selectedIndex !== null && history[selectedIndex] && (
          <ResultView result={history[selectedIndex].result} />
        )}
      </div>
    </main>
  );
}
