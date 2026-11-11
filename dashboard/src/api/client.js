/**
 * API client for FastAPI backend.
 *
 * All calls go through Vite proxy (/api -> http://127.0.0.1:8000)
 * so the browser never needs CORS headers during development.
 */

const BASE = import.meta.env.VITE_API_URL || "/api";

let _token = localStorage.getItem("access_token") || "";

export function setToken(t) {
  _token = t;
  localStorage.setItem("access_token", t);
}

export function getToken() {
  return _token;
}

export function clearToken() {
  _token = "";
  localStorage.removeItem("access_token");
}

async function request(method, path, body = null) {
  const headers = { "Content-Type": "application/json" };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, opts);

  if (res.status === 401) {
    clearToken();
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Auth
  login: (email, password) =>
    request("POST", "/auth/login", { email, password }),

  register: (email, password, role = "operator") =>
    request("POST", "/auth/register", { email, password, role }),

  // Devices & Commands
  getDevices: () => request("GET", "/devices"),
  getDevice: (id) => request("GET", `/devices/${id}`),
  sendCommand: (deviceId, ch, action) =>
    request("POST", `/devices/${deviceId}/commands`, { ch, action }),
  getDeviceMembers: (deviceId) => request("GET", `/devices/${deviceId}/members`),
  shareDevice: (deviceId, email, role) =>
    request("POST", `/devices/${deviceId}/members`, { email, role }),

  // Learning & Safe Limits
  startLearning: (ch, isSimulated = true) =>
    request("POST", `/channels/${ch}/learning/start`, {
      is_simulated: isSimulated,
    }),
  getLearningStatus: (ch) => request("GET", `/channels/${ch}/learning/status`),
  cancelLearning: (sessionId) =>
    request("POST", `/learning/${sessionId}/cancel`),

  // Profiles & Safe Limits Policy (Workstream 3 & 8)
  listProfiles: () => request("GET", "/profiles"),
  confirmProfile: (id) => request("POST", `/profiles/${id}/confirm`),
  updateProfile: (id, data) => request("PATCH", `/profiles/${id}`, data),
  confirmProfileLimits: (id, data = {}) =>
    request("POST", `/profiles/${id}/confirm_limits`, data),
  rejectProfileLimits: (id) =>
    request("POST", `/profiles/${id}/reject_limits`),
  getHealthScore: (profileId, sample) =>
    request("POST", `/profiles/${profileId}/health_score`, { sample }),

  // Schedules (Workstream 7)
  listSchedules: () => request("GET", "/schedules"),
  createSchedule: (data) => request("POST", "/schedules", data),
  updateSchedule: (id, data) => request("PATCH", `/schedules/${id}`, data),
  deleteSchedule: (id) => request("DELETE", `/schedules/${id}`),

  // Recognition
  recognizeWindow: (ch, samples) =>
    request("POST", `/channels/${ch}/recognize`, { samples }),
  getLatestRecognition: (ch) =>
    request("GET", `/channels/${ch}/recognition/latest`),
  getRecognitionHistory: (ch) =>
    request("GET", `/channels/${ch}/recognition/history`),
  submitFeedback: (eventId, feedback, correctedId = null) =>
    request("POST", `/recognition/${eventId}/feedback`, {
      user_feedback: feedback,
      corrected_profile_id: correctedId,
    }),

  // Suggestions
  getChannelSuggestions: (ch) =>
    request("GET", `/channels/${ch}/suggestions`),
  getProfileSuggestions: (profileId) =>
    request("GET", `/profiles/${profileId}/suggestions`),
  acceptSuggestion: (suggestionId) =>
    request("POST", `/suggestions/${suggestionId}/accept`),
  getProfileModes: (profileId) =>
    request("GET", `/profiles/${profileId}/modes`),

  // Anomalies
  checkAnomaly: (ch, sample, profileId = null, isStartup = false) =>
    request("POST", `/channels/${ch}/anomalies/check`, {
      sample,
      profile_id: profileId,
      is_startup_window: isStartup,
    }),
  getAnomalyEvents: (ch) =>
    request("GET", `/channels/${ch}/anomalies/events`),
};

