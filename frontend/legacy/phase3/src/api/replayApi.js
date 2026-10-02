const API_URL = "http://127.0.0.1:8000";

async function readResponse(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string"
      ? payload.detail
      : `Permintaan gagal (${response.status})`;
    throw new Error(detail);
  }
  return payload;
}

async function request(url, options) {
  try {
    return await readResponse(await fetch(url, options));
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Tidak dapat terhubung ke API. Pastikan backend berjalan di port 8000.", { cause: error });
    }
    throw error;
  }
}

export async function importDataset(file, symbol = "XAUUSD", timeframe = "1h", timezone = "UTC") {
  const body = new FormData();
  body.append("file", file);
  body.append("symbol", symbol);
  body.append("timeframe", timeframe);
  body.append("timezone", timezone);

  return request(`${API_URL}/api/datasets/import`, {
    method: "POST",
    body,
  });
}

export async function startReplay(datasetId, settings = {}) {
  return request(`${API_URL}/api/replay/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId, ...settings }),
  });
}

export async function marketOrder(sessionId, order) {
  return request(`${API_URL}/api/replay/${sessionId}/orders/market`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });
}

export async function placePendingOrder(sessionId, order) {
  return request(`${API_URL}/api/replay/${sessionId}/orders/pending`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });
}

export async function cancelPendingOrder(sessionId) {
  return request(`${API_URL}/api/replay/${sessionId}/orders/pending`, {
    method: "DELETE",
  });
}

export async function closePosition(sessionId) {
  return request(`${API_URL}/api/replay/${sessionId}/position/close`, {
    method: "POST",
  });
}

export async function getState(sessionId) {
  return request(`${API_URL}/api/replay/${sessionId}/state`);
}

export async function nextCandle(sessionId) {
  return request(`${API_URL}/api/replay/${sessionId}/next`, {
    method: "POST",
  });
}

export async function previousCandle(sessionId) {
  return request(`${API_URL}/api/replay/${sessionId}/previous`, {
    method: "POST",
  });
}

export async function resetReplay(sessionId) {
  return request(`${API_URL}/api/replay/${sessionId}/reset`, {
    method: "POST",
  });
}
