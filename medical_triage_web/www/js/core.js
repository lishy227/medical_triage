/**
 * core.js — 全局配置、共享状态、基础设施
 *
 * 职责：
 *   1. API 基础 URL 配置（自动区分开发/生产环境）
 *   2. Capacitor 混合应用环境检测
 *   3. 会话状态管理（sessionId、isWaiting、currentStage）
 *   4. HTTP 请求封装（兼容 Capacitor 原生 HTTP）
 *   5. 服务器重启检测（定期轮询 + 自动退出登录）
 *
 * 所有其他模块通过 import 获取导出的函数和状态。
 *
 * @module core
 */

// ============================================================================
// 全局配置
// ============================================================================

/**
 * API 基础 URL
 *
 * 自动根据当前页面 hostname 选择：
 *   - localhost           → http://localhost:5001        （本地开发）
 *   - 其他（服务器/局域网） → http://<hostname>:5001       （生产环境）
 */
export const API_BASE =
  window.location.hostname === "localhost"
    ? "http://localhost:5001"
    : `http://${window.location.hostname}:5001`;

// ============================================================================
// Capacitor 混合应用支持
// ============================================================================

/**
 * Capacitor 原生 HTTP 插件引用
 *
 * 在 Capacitor 打包的 Android/iOS App 中运行时，
 * 使用原生 HTTP 层发请求可以绕过 WebView 的 CORS 限制。
 *
 * @type {object|null}
 */
export let CapacitorHttp = null;
if (typeof window !== "undefined" && window.Capacitor) {
  CapacitorHttp = window.Capacitor.Plugins?.Http ?? null;
}

// ============================================================================
// 会话 / 应用状态
// ============================================================================

/** 当前导诊会话 ID，每次页面加载重新生成 */
export let sessionId = generateSessionId();

/** 是否正在等待后端响应（防止重复提交） */
export let isWaiting = false;

/** 设置 isWaiting */
export function setWaiting(val) {
  isWaiting = val;
}

/** 当前导诊阶段（0: 身体部位, 1: 初步症状, 2: 具体症状, 3: 完成） */
export let currentStage = 0;

/** 设置 currentStage */
export function setCurrentStage(stage) {
  currentStage = stage;
}

// ============================================================================
// 服务器重启检测
// ============================================================================

/** localStorage 键：存储后端实例 UUID */
const SERVER_INSTANCE_KEY = "server_instance_id";

/** 服务器状态检测间隔（毫秒） */
const SERVER_CHECK_INTERVAL = 30_000;

/**
 * 检测后端服务器是否重启
 *
 * 后端每次启动生成唯一 instance_id，前端本地缓存该 ID。
 * 若轮询发现 ID 变化，说明服务器已重启，内存中的会话全部丢失，
 * 需要引导用户重新登录。
 *
 * @returns {Promise<boolean>} true = 服务器已重启
 */
export async function checkServerRestart() {
  try {
    const resp = await fetch(`${API_BASE}/api/server/info`);
    const data = await resp.json();
    const stored = localStorage.getItem(SERVER_INSTANCE_KEY);
    const current = data.instance_id;

    if (!stored) {
      localStorage.setItem(SERVER_INSTANCE_KEY, current);
      return false;
    }
    if (stored !== current) {
      console.log("[core] 检测到服务器重启，即将自动退出登录");
      localStorage.setItem(SERVER_INSTANCE_KEY, current);
      return true;
    }
    return false;
  } catch {
    // 网络不可达时不误判为重启
    return false;
  }
}

/**
 * 执行自动退出登录（服务器重启触发）
 *
 * 清除本地 Token 和用户状态，1.5 秒后刷新页面。
 */
export function autoLogout() {
  const hadToken = localStorage.getItem("auth_token");
  localStorage.removeItem("auth_token");
  // 注意：auth 模块的 currentUser 需在 app.js 入口统一清
  if (hadToken) {
    // 页面刷新会在 app.js 入口触发，此处只做标记
    setTimeout(() => window.location.reload(), 1500);
  }
}

/**
 * 启动定期服务器状态检测
 *
 * 页面加载时立即检查一次，之后每 30 秒轮询。
 */
export function startServerCheck(onRestartDetected) {
  checkServerRestart().then((restarted) => {
    if (restarted && onRestartDetected) onRestartDetected();
  });
  setInterval(async () => {
    const restarted = await checkServerRestart();
    if (restarted && onRestartDetected) onRestartDetected();
  }, SERVER_CHECK_INTERVAL);
}

// ============================================================================
// 工具函数
// ============================================================================

/**
 * 生成唯一会话 ID
 *
 * 格式: session_<timestamp>_<random>
 *
 * @returns {string}
 */
export function generateSessionId() {
  return (
    "session_" +
    Date.now() +
    "_" +
    Math.random().toString(36).substring(2, 11)
  );
}

/**
 * 从 localStorage 读取认证 Token
 *
 * @returns {string}
 */
export function getAuthToken() {
  try {
    return localStorage.getItem("auth_token") || "";
  } catch {
    return "";
  }
}

/**
 * 构建带认证头的 Headers
 *
 * @param {Record<string,string>} [extra={}] 额外请求头
 * @returns {Record<string,string>}
 */
export function buildAuthHeaders(extra = {}) {
  const token = getAuthToken();
  return token
    ? { ...extra, Authorization: `Bearer ${token}` }
    : { ...extra };
}

// ============================================================================
// HTTP 请求封装
// ============================================================================

/**
 * 统一的 HTTP 请求函数
 *
 *   - Capacitor App 内 → 使用原生 HTTP 插件（绕过 CORS）
 *   - 浏览器环境      → 使用标准 fetch
 *
 * @param {string} url       - 完整请求 URL
 * @param {object} [options] - fetch 选项 (method, headers, body, …)
 * @returns {Promise<{json: ()=>Promise<any>}>} 兼容 fetch response 的 { json() } 接口
 */
export async function httpRequest(url, options = {}) {
  if (CapacitorHttp) {
    const resp = await CapacitorHttp.request({
      url,
      method: options.method || "GET",
      headers: options.headers || {},
      data: options.body ? JSON.parse(options.body) : undefined,
    });
    return { json: () => Promise.resolve(resp.data) };
  }
  return fetch(url, options);
}
