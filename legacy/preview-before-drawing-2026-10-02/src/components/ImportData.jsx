import { useState } from "react";
import { importDataset, startReplay } from "../api/replayApi";

function ImportData({ onReplayStarted, onStatus }) {
  const [file, setFile] = useState(null);
  const [symbol, setSymbol] = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("1h");
  const [timezone, setTimezone] = useState("UTC");
  const [initialBalance, setInitialBalance] = useState("10000");
  const [contractSize, setContractSize] = useState("100");
  const [spread, setSpread] = useState("0");
  const [slippage, setSlippage] = useState("0");
  const [commission, setCommission] = useState("0");
  const [busy, setBusy] = useState(false);

  async function importFile(selectedFile, importOptions = { symbol, timeframe, timezone }) {
    setBusy(true);
    onStatus("Memeriksa dan mengimpor file…");
    try {
      const imported = await importDataset(selectedFile, importOptions.symbol, importOptions.timeframe, importOptions.timezone);
      if (!imported.ok) {
        const issues = imported.report?.issues ?? [];
        const firstError = issues.find((issue) => issue.severity === "error");
        throw new Error(firstError?.message ?? "File tidak dapat diimpor.");
      }

      const replay = await startReplay(imported.dataset_id, {
        initial_balance: Number(initialBalance),
        contract_size: Number(contractSize),
        spread: Number(spread),
        slippage: Number(slippage),
        commission_per_lot: Number(commission),
      });
      onReplayStarted(replay, imported.report);
      onStatus(`Berhasil memuat ${imported.report.valid_rows} candle. Replay siap.`, "success");
    } catch (error) {
      onStatus(error.message || "Tidak dapat terhubung ke API Backtest Lab.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(event) {
    event.preventDefault();
    if (!file) {
      onStatus("Pilih file CSV terlebih dahulu.", "error");
      return;
    }
    await importFile(file);
  }

  async function loadSampleData() {
    setBusy(true);
    onStatus("Memuat data contoh XAUUSD…");
    try {
      const response = await fetch("/sample_XAUUSD_1h.csv");
      if (!response.ok) throw new Error("File data contoh tidak ditemukan.");
      const sampleFile = new File([await response.blob()], "sample_XAUUSD_1h.csv", { type: "text/csv" });
      setFile(sampleFile);
      await importFile(sampleFile, { symbol: "XAUUSD", timeframe: "1h", timezone: "UTC" });
    } catch (error) {
      onStatus(error.message || "Data contoh tidak dapat dimuat.", "error");
      setBusy(false);
    }
  }

  return (
    <form className="import-form" onSubmit={handleImport}>
      <label className="file-picker">
        <span>Data CSV</span>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
      <label>
        Instrumen
        <input value={symbol} onChange={(event) => setSymbol(event.target.value)} maxLength={24} />
      </label>
      <label>
        Timeframe
        <select value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
          {["1m", "5m", "15m", "30m", "1h", "4h", "1d"].map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
      </label>
      <label>
        Zona waktu CSV
        <input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="UTC / Asia/Jakarta" />
      </label>
      <details className="account-settings">
        <summary>Pengaturan akun & biaya</summary>
        <div className="settings-grid">
          <label>Saldo awal
            <input type="number" min="0.01" step="any" value={initialBalance} onChange={(event) => setInitialBalance(event.target.value)} />
          </label>
          <label>Ukuran kontrak
            <input type="number" min="0.001" step="any" value={contractSize} onChange={(event) => setContractSize(event.target.value)} />
          </label>
          <label>Spread (harga)
            <input type="number" min="0" step="any" value={spread} onChange={(event) => setSpread(event.target.value)} />
          </label>
          <label>Slippage (harga)
            <input type="number" min="0" step="any" value={slippage} onChange={(event) => setSlippage(event.target.value)} />
          </label>
          <label>Komisi / lot / sisi
            <input type="number" min="0" step="any" value={commission} onChange={(event) => setCommission(event.target.value)} />
          </label>
        </div>
        <p>Nilai biaya memakai satuan harga dataset; komisi dikenakan saat buka dan tutup posisi.</p>
      </details>
      <div className="import-submit-actions">
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "Memuat…" : "Impor & mulai"}
        </button>
        <button className="sample-data-button" type="button" onClick={loadSampleData} disabled={busy}>
          Pakai data contoh
        </button>
      </div>
      <span className="selected-file">{file?.name ?? "Belum ada file dipilih"}</span>
    </form>
  );
}

export default ImportData;
