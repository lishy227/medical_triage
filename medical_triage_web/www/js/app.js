/**
 * app.js — 应用入口
 *
 * 职责：
 *   1. 初始化所有模块
 *   2. 绑定事件监听器
 *   3. 暴露必要的全局引用（供 HTML onclick 使用）
 *   4. 启动认证恢复 + 服务器重启检测
 *   5. 触发首次欢迎消息加载
 *
 * 模块加载顺序：
 *   core → ui → auth → chat → social → app（本文件）
 *
 * @module app
 */

import { generateSessionId, checkServerRestart, startServerCheck, autoLogout } from "./core.js";
import {
  initDomRefs,
  userInput,
  handleKeyDown,
  openAuthModal,
  closeAuthModal,
  switchAuthMode,
  openProfilePanel,
  closeProfilePanel,
  openUpgradeModal,
  closeUpgradeModal,
  showLoading,
  hideLoading,
} from "./ui.js";
import {
  getStoredToken,
  setCurrentUser,
  bootstrapAuth,
  submitAuthForm,
  logout,
  loadProfileAndHistory,
  loadHistory,
  submitUpgrade,
} from "./auth.js";
import {
  loadWelcomeMessage,
  sendMessage,
  resetChat,
  bindInputAutoResize,
} from "./chat.js";
import {
  openCommentsCommunity,
  openCommentsModalFor,
  closeCommentsModalExternal,
  toggleCommentLike,
  replyToComment,
  loadReplies,
} from "./social.js";

// ============================================================================
// 初始化
// ============================================================================

/**
 * 应用启动入口
 *
 * 执行顺序：
 *   1. 注入 sessionId 到全局（供 chat 模块使用）
 *   2. 初始化 DOM 引用缓存
 *   3. 绑定事件
 *   4. 检查服务器是否重启 → 是则刷新
 *   5. 恢复登录状态
 *   6. 加载欢迎消息
 *   7. 聚焦输入框
 *   8. 启动 30 秒一次的服务器状态检测
 */
async function bootstrap() {
  // 全局会话 ID
  window.__sessionId = generateSessionId();

  // DOM 引用
  initDomRefs();

  // 绑定事件
  bindInputAutoResize();
  if (userInput) {
    userInput.addEventListener("keydown", (e) =>
      handleKeyDown(e, sendMessage),
    );
  }

  // 服务器重启检测
  const restarted = await checkServerRestart();
  if (restarted) {
    autoLogout();
    return;
  }

  // 恢复认证
  await bootstrapAuth();

  // 加载欢迎消息（仅在已登录时）
  await loadWelcomeMessage();

  if (userInput) userInput.focus();

  // 启动定期服务器检测
  startServerCheck(() => autoLogout());
}

// ============================================================================
// 全局 API 暴露（供 HTML onclick 属性调用）
// ============================================================================

// -- 认证 --
window.Auth = {
  submitAuthForm,
  logout,
  loadProfileAndHistory,
  loadHistory,
  submitUpgrade,
};

// -- UI 工具 --
window.UI = {
  openAuthModal,
  closeAuthModal,
  switchAuthMode,
  openProfilePanel,
  closeProfilePanel,
  openUpgradeModal: () => openUpgradeModal(submitUpgrade),
  closeUpgradeModal,
  showLoading,
  hideLoading,
};

// -- 聊天 --
window.Chat = {
  sendMessage,
  resetChat,
};

// -- 社交 --
window.Social = {
  openCommentsCommunity,
  openCommentsModal: openCommentsModalFor,
  closeCommentsModal: closeCommentsModalExternal,
  replyToComment,
  toggleCommentLike,
  loadReplies,
};

// ============================================================================
// 启动
// ============================================================================

document.addEventListener("DOMContentLoaded", bootstrap);
