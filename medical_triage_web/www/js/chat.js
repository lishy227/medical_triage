/**
 * chat.js — 导诊对话核心逻辑
 *
 * 职责：
 *   1. 加载欢迎消息（需登录）
 *   2. 发送导诊消息 → 调用 /api/chat → 渲染回复
 *   3. 重置对话 → 调用 /api/reset → 清空 UI
 *   4. 登录门控：未登录时拦截 chat/welcome/reset 操作
 *
 * 本模块不直接操作 DOM，所有渲染委托给 ui 模块。
 * 认证检查委托给 auth 模块。
 *
 * @module chat
 */

import { API_BASE, isWaiting, setWaiting } from "./core.js";
import { httpRequest, buildAuthHeaders } from "./core.js";
import {
  userInput,
  sendBtn,
  messagesContainer,
  showLoading,
  hideLoading,
  addUserMessage,
  addBotMessage,
  addSystemMessage,
  addCompleteMessage,
  addTypingIndicator,
  removeTypingIndicator,
  updateStage,
  escapeHtml,
  openAuthModal,
} from "./ui.js";
import { getStoredToken, currentUser } from "./auth.js";

// ============================================================================
// 欢迎消息
// ============================================================================

/**
 * 从后端获取欢迎消息并更新页面
 *
 * 仅在已登录时调用；未登录时直接返回。
 */
export async function loadWelcomeMessage() {
  if (!getStoredToken()) return;

  try {
    showLoading();
    const resp = await httpRequest(
      `${API_BASE}/api/welcome?session_id=${window.__sessionId || "default"}`,
      { headers: buildAuthHeaders() },
    );
    const data = await resp.json();
    const bubble = document.querySelector(".system-message .message-bubble");
    if (bubble && data.message) {
      bubble.innerHTML = `<p>${escapeHtml(data.message)}</p>`;
    }
  } catch (err) {
    console.error("[chat] 加载欢迎消息失败:", err);
  } finally {
    hideLoading();
  }
}

// ============================================================================
// 发送消息
// ============================================================================

/**
 * 发送用户消息到后端导诊引擎
 *
 * 流程：
 *   1. 校验登录 → 未登录弹出登录框
 *   2. 校验消息非空、非重复提交
 *   3. POST /api/chat { session_id, message }
 *   4. 根据响应更新阶段指示器、渲染回复或完成卡片
 *   5. 错误处理 + 网络异常提示
 */
export async function sendMessage() {
  // ---- 登录门控 ----
  if (!getStoredToken()) {
    openAuthModal("login");
    addSystemMessage("请先登录，再开始导诊。");
    return;
  }

  const message = userInput.value.trim();
  if (!message || isWaiting) return;

  // ---- 添加用户消息 ----
  addUserMessage(message);
  userInput.value = "";
  userInput.style.height = "auto";

  // ---- 发送请求 ----
  setWaiting(true);
  sendBtn.disabled = true;
  const typingId = addTypingIndicator();

  try {
    const resp = await httpRequest(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        session_id: window.__sessionId || "default",
        message,
      }),
    });
    const data = await resp.json();
    removeTypingIndicator(typingId);

    if (data.error) {
      addBotMessage("抱歉，出现了错误：" + data.error);
      return;
    }

    // 更新阶段指示器
    if (data.stage !== undefined) {
      updateStage(data.stage);
    }

    // 渲染回复
    if (data.is_complete) {
      addCompleteMessage(
        data.message,
        data.records,
        data,
        window.__sessionId,
      );
    } else {
      addBotMessage(data.message);
    }
  } catch (err) {
    removeTypingIndicator(typingId);
    addBotMessage("抱歉，网络连接出现问题，请稍后重试。");
    console.error("[chat] 发送消息失败:", err);
  } finally {
    setWaiting(false);
    sendBtn.disabled = false;
    userInput.focus();
  }
}

// ============================================================================
// 重置对话
// ============================================================================

/**
 * 重置导诊对话
 *
 * 调用 POST /api/reset → 清空消息区域 → 显示新欢迎消息 → 重置阶段为 0
 */
export async function resetChat() {
  if (!getStoredToken()) {
    messagesContainer.innerHTML = "";
    addSystemMessage("请先登录，再开始新的导诊会话。");
    return;
  }

  if (isWaiting) return;

  try {
    showLoading();
    const resp = await httpRequest(`${API_BASE}/api/reset`, {
      method: "POST",
      headers: buildAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        session_id: window.__sessionId || "default",
      }),
    });
    const data = await resp.json();

    messagesContainer.innerHTML = "";
    addSystemMessage(data.message);
    updateStage(0);
  } catch (err) {
    console.error("[chat] 重置失败:", err);
    addBotMessage("重置失败，请刷新页面重试。");
  } finally {
    hideLoading();
    userInput.focus();
  }
}

// ============================================================================
// 输入框自适应高度
// ============================================================================

/**
 * 绑定输入框 auto-resize 事件
 * （在 app.js 入口调用一次即可）
 */
export function bindInputAutoResize() {
  userInput.addEventListener("input", () => {
    userInput.style.height = "auto";
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + "px";
  });
}
