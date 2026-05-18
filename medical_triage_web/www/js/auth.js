/**
 * auth.js — 用户认证与个人中心
 *
 * 职责：
 *   1. Token 持久化（localStorage 读写）
 *   2. 登录 / 注册 / 登出
 *   3. 用户状态管理（currentUser）
 *   4. 带认证的统一 fetch 封装（authFetch）
 *   5. 个人中心数据加载（资料 + 历史记录）
 *   6. 会员升级
 *   7. 启动时的 Token 恢复（bootstrapAuth）
 *
 * 与 ui 模块解耦：本模块负责数据逻辑，
 * UI 更新通过调用 ui 模块的渲染函数完成。
 *
 * @module auth
 */

import { API_BASE } from "./core.js";
import {
  showLoading,
  hideLoading,
  addSystemMessage,
  updateAuthUI,
  openAuthModal,
  closeAuthModal,
  setAuthError,
  getAuthMode,
  renderProfile,
  renderHistory,
  updateStage,
  formatDateTime,
  getErrorMessage,
  openUpgradeModal,
  closeUpgradeModal,
} from "./ui.js";

// ============================================================================
// 用户状态
// ============================================================================

/**
 * 当前登录用户数据（{ id, username, membership_type, … }）
 * @type {object|null}
 */
export let currentUser = null;

/**
 * @param {object|null} user
 */
export function setCurrentUser(user) {
  currentUser = user || null;
  updateAuthUI(currentUser);
}

// ============================================================================
// Token 管理
// ============================================================================

/**
 * 从 localStorage 读取 JWT Token
 * @returns {string}
 */
export function getStoredToken() {
  return localStorage.getItem("auth_token") || "";
}

/**
 * 写入或清除 JWT Token
 * @param {string} token - 空字符串表示清除
 */
export function setStoredToken(token) {
  if (token) {
    localStorage.setItem("auth_token", token);
  } else {
    localStorage.removeItem("auth_token");
  }
}

// ============================================================================
// 统一的认证 fetch
// ============================================================================

/**
 * 带 Token 的 HTTP 请求封装
 *
 * 自动附加 Authorization: Bearer 头；
 * 若收到 401 则清除本地 Token 和用户状态；
 * 网络错误包装为统一的 { error } 对象。
 *
 * @param {string} path     - API 路径（如 '/api/auth/login'）
 * @param {object} [options] - fetch 选项
 * @returns {Promise<any>} 解析后的 JSON 响应
 * @throws {{error:string}} 网络错误或业务错误
 */
export async function authFetch(path, options = {}) {
  const token = getStoredToken();
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let resp;
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (netErr) {
    console.error("[auth] 网络请求失败:", netErr);
    throw { error: "无法连接到服务器，请检查网络或稍后重试", details: String(netErr) };
  }

  let data = {};
  try {
    data = await resp.json();
  } catch {
    /* 非 JSON 响应 */
  }

  if (!resp.ok) {
    if (resp.status === 401) {
      setStoredToken("");
      setCurrentUser(null);
    }
    throw data.error ? data : { error: `服务器错误 (${resp.status})` };
  }

  return data;
}

// ============================================================================
// 登录 / 注册
// ============================================================================

/**
 * 提交登录或注册表单
 * @param {Event} event - 表单 submit 事件
 */
export async function submitAuthForm(event) {
  event.preventDefault();
  setAuthError("");

  const username = document.getElementById("authUsername").value.trim();
  const password = document.getElementById("authPassword").value;

  if (!username || !password) {
    setAuthError("用户名和密码不能为空");
    return;
  }

  const mode = getAuthMode();
  const path = mode === "register" ? "/api/auth/register" : "/api/auth/login";

  try {
    showLoading();
    const data = await authFetch(path, {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });

    setStoredToken(data.token || "");
    setCurrentUser(data.user || null);
    closeAuthModal();
    document.getElementById("authUsername").value = "";
    document.getElementById("authPassword").value = "";
    addSystemMessage(
      data.message || (mode === "register" ? "注册成功" : "登录成功"),
    );
  } catch (err) {
    console.error("[auth] 登录/注册失败:", err);
    setAuthError(getErrorMessage(err));
  } finally {
    hideLoading();
  }
}

/**
 * 登出
 */
export async function logout() {
  try {
    showLoading();
    await authFetch("/api/auth/logout", { method: "POST" });
  } catch {
    // 即使后端登出失败也清除本地态
  } finally {
    setStoredToken("");
    setCurrentUser(null);
    hideLoading();
    addSystemMessage("您已退出登录");
  }
}

// ============================================================================
// 个人中心
// ============================================================================

/**
 * 加载用户资料并渲染
 */
export async function loadProfile() {
  const data = await authFetch("/api/user/center");
  const user = data.user || {};
  const summary = data.summary || {};
  setCurrentUser(user);
  renderProfile(user, summary, formatDateTime);
}

/**
 * 加载历史记录并渲染
 * @param {boolean} [silent=false] - 静默模式（失败不弹消息）
 */
export async function loadHistory(silent = false) {
  try {
    const data = await authFetch("/api/user/history");
    renderHistory(data.history || [], formatDateTime);
    if (typeof data.count === "number") {
      document.getElementById("profileHistoryCount").textContent =
        String(data.count);
    }
  } catch (err) {
    if (!silent) {
      addSystemMessage(getErrorMessage(err, "加载历史记录失败"));
    }
    throw err;
  }
}

/**
 * 同时加载资料和历史记录（打开个人中心时调用）
 */
export async function loadProfileAndHistory() {
  try {
    showLoading();
    await loadProfile();
    await loadHistory(true);
  } catch (err) {
    addSystemMessage(getErrorMessage(err, "加载个人中心失败"));
  } finally {
    hideLoading();
  }
}

// ============================================================================
// 启动认证恢复
// ============================================================================

/**
 * 页面加载时恢复登录状态
 *
 * 若 localStorage 中有 Token，调用 /api/auth/profile 验证有效性；
 * 若 Token 无效则清除。
 */
export async function bootstrapAuth() {
  const token = getStoredToken();
  if (!token) {
    setCurrentUser(null);
    return;
  }
  try {
    const data = await authFetch("/api/auth/profile");
    setCurrentUser(data.user || null);
  } catch {
    setStoredToken("");
    setCurrentUser(null);
  }
}

// ============================================================================
// 会员升级
// ============================================================================

/**
 * 提交会员升级
 */
export async function submitUpgrade() {
  try {
    showLoading();
    const data = await authFetch("/api/membership/upgrade", {
      method: "POST",
    });
    setCurrentUser(data.user || null);
    closeUpgradeModal();
    addSystemMessage(
      "🎉 " +
        (data.message || "会员升级成功！现在您可以享受详细的医疗建议服务。"),
    );
  } catch (err) {
    console.error("[auth] 升级失败:", err);
    alert(getErrorMessage(err, "升级失败，请稍后重试"));
  } finally {
    hideLoading();
  }
}

/**
 * 获取会员状态
 * @returns {Promise<object|null>}
 */
export async function checkMembershipStatus() {
  try {
    return await authFetch("/api/membership/status");
  } catch (err) {
    console.error("[auth] 获取会员状态失败:", err);
    return null;
  }
}
