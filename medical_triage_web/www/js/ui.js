/**
 * ui.js — UI 渲染与 DOM 操作
 *
 * 职责：
 *   1. HTML 转义 / 消息格式化
 *   2. 消息气泡渲染（用户/系统/机器人/完成卡片）
 *   3. 打字指示器（三个点的动画）
 *   4. 阶段指示器更新（侧边栏步骤条）
 *   5. 弹窗管理（登录/注册、个人中心、会员升级、评论社区）
 *   6. 历史记录列表渲染
 *   7. 加载遮罩层
 *   8. 认证 UI 状态切换
 *
 * 本模块不直接持有业务状态（如 currentUser），
 * 需要从 auth / chat / social 模块传入。
 *
 * @module ui
 */

import { currentStage, setCurrentStage } from "./core.js";

// ============================================================================
// DOM 引用缓存（页面加载后由 app.js 调用 initDomRefs 设置）
// ============================================================================

/** @type {HTMLElement} */
export let messagesContainer = null;
/** @type {HTMLTextAreaElement} */
export let userInput = null;
/** @type {HTMLButtonElement} */
export let sendBtn = null;
/** @type {HTMLElement} */
export let loadingOverlay = null;

/**
 * 初始化 DOM 引用
 * 必须在 DOMContentLoaded 之后调用
 */
export function initDomRefs() {
  messagesContainer = document.getElementById("messages");
  userInput = document.getElementById("userInput");
  sendBtn = document.getElementById("sendBtn");
  loadingOverlay = document.getElementById("loading");
}

// ============================================================================
// HTML 工具
// ============================================================================

/**
 * 转义 HTML 特殊字符，防止 XSS
 *
 * 使用浏览器原生 textContent → innerHTML 机制，
 * 比正则替换更可靠（覆盖所有 HTML 实体）。
 *
 * @param {string} text 原始文本
 * @returns {string} 转义后的安全 HTML 字符串
 */
export function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * 格式化聊天消息（换行 → <p> 标签包裹）
 *
 * @param {string} text
 * @returns {string} HTML 字符串
 */
export function formatMessage(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  html = html.replace(/\n/g, "</p><p>");
  if (!html.startsWith("<p>")) html = "<p>" + html;
  if (!html.endsWith("</p>")) html += "</p>";
  return html;
}

/**
 * 获取当前时间（中文格式 HH:MM）
 * @returns {string}
 */
export function getCurrentTime() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ============================================================================
// 加载动画
// ============================================================================

/** 显示全屏加载遮罩 */
export function showLoading() {
  loadingOverlay?.classList.add("active");
}

/** 隐藏全屏加载遮罩 */
export function hideLoading() {
  loadingOverlay?.classList.remove("active");
}

// ============================================================================
// 消息渲染
// ============================================================================

/**
 * 添加用户消息到聊天区域
 * @param {string} text
 */
export function addUserMessage(text) {
  const div = document.createElement("div");
  div.className = "message user-message";
  div.innerHTML = `
    <div class="message-avatar">👤</div>
    <div class="message-content">
      <div class="message-bubble">${escapeHtml(text)}</div>
      <div class="message-time">${getCurrentTime()}</div>
    </div>`;
  messagesContainer.appendChild(div);
  scrollToBottom();
}

/**
 * 添加系统消息（如欢迎语、提示）
 * @param {string} text
 */
export function addSystemMessage(text) {
  const div = document.createElement("div");
  div.className = "message system-message";
  div.innerHTML = `
    <div class="message-avatar">🏥</div>
    <div class="message-content">
      <div class="message-bubble">${formatMessage(text)}</div>
      <div class="message-time">${getCurrentTime()}</div>
    </div>`;
  messagesContainer.appendChild(div);
  scrollToBottom();
}

/**
 * 添加机器人/助手消息
 * @param {string} text
 */
export function addBotMessage(text) {
  const div = document.createElement("div");
  div.className = "message bot-message";
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="message-bubble">${formatMessage(text)}</div>
      <div class="message-time">${getCurrentTime()}</div>
    </div>`;
  messagesContainer.appendChild(div);
  scrollToBottom();
}

// ============================================================================
// 打字指示器
// ============================================================================

/**
 * 添加"正在输入..."打字动画
 * @returns {string} 元素 ID，用于后续移除
 */
export function addTypingIndicator() {
  const id = "typing-" + Date.now();
  const div = document.createElement("div");
  div.className = "message bot-message";
  div.id = id;
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="message-bubble">
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>`;
  messagesContainer.appendChild(div);
  scrollToBottom();
  return id;
}

/**
 * 移除打字指示器
 * @param {string} id
 */
export function removeTypingIndicator(id) {
  document.getElementById(id)?.remove();
}

// ============================================================================
// 完成结果卡片
// ============================================================================

/**
 * 渲染详细医疗建议（会员专享内容）
 *
 * 从后端返回的 detailed_medical_advice 对象渲染疾病卡片、
 * 饮食建议、就医提示。
 *
 * @param {object} advice - 后端 generate_detailed_advice() 的返回值
 * @returns {string} HTML
 */
export function renderDetailedAdvice(advice) {
  if (!advice || typeof advice !== "object") return "";

  let html = '<div class="detailed-advice">';

  // ---- 可能的相关疾病 ----
  if (advice.possible_diseases?.length) {
    html += '<div class="advice-section"><h4>🔍 可能的相关疾病</h4>';
    advice.possible_diseases.forEach((d, i) => {
      html += `
        <div class="disease-card">
          <div class="disease-name">${i + 1}. ${escapeHtml(d.name)}</div>
          <div class="disease-desc">${escapeHtml(d.description)}</div>
          ${d.symptoms?.length ? `<div class="disease-symptoms"><strong>症状：</strong>${d.symptoms.map(escapeHtml).join("、")}</div>` : ""}
          ${d.cure_way?.length ? `<div class="disease-cure"><strong>治疗方式：</strong>${d.cure_way.map(escapeHtml).join("、")}</div>` : ""}
          ${d.cure_lasttime ? `<div class="disease-duration"><strong>治疗周期：</strong>${escapeHtml(d.cure_lasttime)}</div>` : ""}
          ${d.cured_prob ? `<div class="disease-rate"><strong>治愈率：</strong>${escapeHtml(d.cured_prob)}</div>` : ""}
          ${d.cost_money ? `<div class="disease-cost"><strong>参考费用：</strong>${escapeHtml(d.cost_money)}</div>` : ""}
        </div>`;
    });
    html += "</div>";
  }

  // ---- 饮食建议 ----
  if (advice.diet_suggestions) {
    html += '<div class="advice-section"><h4>🍽️ 饮食建议</h4>';
    if (advice.diet_suggestions.recommended?.length) {
      html += `<div class="diet-recommended"><strong>推荐食用：</strong>${advice.diet_suggestions.recommended.map(escapeHtml).join("、")}</div>`;
    }
    if (advice.diet_suggestions.avoid?.length) {
      html += `<div class="diet-avoid"><strong>建议避免：</strong>${advice.diet_suggestions.avoid.map(escapeHtml).join("、")}</div>`;
    }
    html += "</div>";
  }

  // ---- 就医建议 ----
  if (advice.general_tips?.length) {
    html += '<div class="advice-section"><h4>💡 就医建议</h4><ul class="tips-list">';
    advice.general_tips.forEach((t) => (html += `<li>${escapeHtml(t)}</li>`));
    html += "</ul></div>";
  }

  html += "</div>";
  return html;
}

/**
 * 从文本中提取推荐科室列表
 * @param {string} text
 * @returns {string[]}
 */
export function extractDepartmentsFromText(text) {
  const m = String(text || "").match(/最终推荐结果:\s*\[(.*?)\]/);
  if (!m?.[1]) return [];
  return m[1]
    .split(",")
    .map((d) => d.trim().replace(/['"]/g, ""))
    .filter(Boolean);
}

/**
 * 添加"导诊完成"结果卡片消息
 *
 * @param {string} text    - 后端返回的原始消息
 * @param {string[]} records - 导诊记录数组
 * @param {object} result  - 后端 /api/chat 的完整响应
 * @param {string} [sessionIdForComment] - 用于关联评论的会话 ID
 */
export function addCompleteMessage(text, records, result, sessionIdForComment) {
  const departments =
    Array.isArray(result.departments) && result.departments.length
      ? result.departments
      : extractDepartmentsFromText(text);

  const firstDept = departments[0] || "暂无推荐";
  const detailLocked = !!result.detail_locked;
  const detailedAdvice = result.detailed_medical_advice;
  const summary = result.conversation_summary || "";
  const detailLevel = result.detail_level || (detailLocked ? "basic" : "member");

  // 过滤掉后端格式行，保留自然语言摘要
  const lines = String(text || "").split("\n");
  let mainMsg = "";
  for (const line of lines) {
    if (line.includes("最终推荐结果:") || line.includes("收集信息:")) continue;
    mainMsg += line + "\n";
  }

  const detailBlock = detailLocked
    ? `
      <div class="member-lock-box">
        <div class="member-lock-title">🔒 详细建议为会员专享内容</div>
        <div class="member-lock-text">当前仅展示推荐科室。开通会员后，可查看完整疾病分析、治疗建议、饮食指导等详细内容。</div>
        <button class="upgrade-btn" onclick="window.UI.openUpgradeModal()">✨ 立即开通会员</button>
      </div>`
    : detailedAdvice
      ? renderDetailedAdvice(detailedAdvice)
      : "";

  const summaryBlock = summary
    ? `<div class="summary-text">问诊摘要：${escapeHtml(summary)}</div>`
    : "";

  const badgeText = detailLevel === "member" ? "会员详细版" : "基础版";
  const badgeClass =
    detailLevel === "member" ? "detail-badge member" : "detail-badge basic";

  const commentTargetId = sessionIdForComment || "default";

  const div = document.createElement("div");
  div.className = "message bot-message";
  div.innerHTML = `
    <div class="message-avatar">🎉</div>
    <div class="message-content">
      <div class="message-bubble">
        <p>${formatMessage(mainMsg.trim() || text || "")}</p>
        <div class="result-card">
          <div class="result-card-header">
            <h3>🏥 推荐就诊科室</h3>
            <span class="${badgeClass}">${badgeText}</span>
          </div>
          <div class="departments">
            ${departments.map((d) => `<span class="dept-tag">${escapeHtml(d)}</span>`).join("") || `<span class="dept-tag">${escapeHtml(firstDept)}</span>`}
          </div>
          ${summaryBlock}
          ${detailBlock}
          <div class="result-actions">
            <button class="comment-trigger-btn" onclick="window.Social.openCommentsModal('triage','${commentTargetId}','导诊评论')">
              💬 评论
            </button>
          </div>
        </div>
      </div>
      <div class="message-time">${getCurrentTime()}</div>
    </div>`;
  messagesContainer.appendChild(div);
  scrollToBottom();
}

// ============================================================================
// 阶段指示器
// ============================================================================

/**
 * 更新侧边栏阶段指示器
 * @param {number} stage - 0..3
 */
export function updateStage(stage) {
  setCurrentStage(stage);
  document.querySelectorAll(".step").forEach((step, i) => {
    step.classList.remove("active", "completed");
    const num = step.querySelector(".step-num");
    if (i < stage) {
      step.classList.add("completed");
      num.textContent = "✓";
    } else if (i === stage) {
      step.classList.add("active");
      num.textContent = String(i + 1);
    } else {
      num.textContent = String(i + 1);
    }
  });
}

// ============================================================================
// 滚动 & 键盘
// ============================================================================

/** 将聊天区域滚动到底部 */
export function scrollToBottom() {
  if (messagesContainer) {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

/**
 * 输入框键盘事件处理
 *   Enter        → 发送
 *   Shift+Enter  → 换行
 *
 * @param {KeyboardEvent} event
 * @param {()=>void} onSend - 发送回调
 */
export function handleKeyDown(event, onSend) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (onSend) onSend();
  }
}

// ============================================================================
// 认证 UI 状态
// ============================================================================

/**
 * 根据当前用户更新顶部认证栏 UI
 *
 * @param {object|null} user - 用户数据（含 username, membership_type）
 */
export function updateAuthUI(user) {
  const isMember = user?.membership_type === "member";
  const statusText = user
    ? isMember
      ? `✨ 会员：${user.username}`
      : `已登录：${user.username}`
    : "未登录";

  const setText = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  };
  const toggle = (id, show) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("hidden", !show);
  };

  setText("authStatusText", statusText);
  toggle("loginBtn", !user);
  toggle("registerBtn", !user);
  toggle("profileBtn", !!user);
  toggle("logoutBtn", !!user);
}

// ============================================================================
// 弹窗：登录 / 注册
// ============================================================================

let _authMode = "login";

export function switchAuthMode(mode) {
  _authMode = mode === "register" ? "register" : "login";
  document.getElementById("authModalTitle").textContent =
    _authMode === "register" ? "注册" : "登录";
  document.getElementById("authSubmitBtn").textContent =
    _authMode === "register" ? "注册" : "登录";
  document
    .getElementById("authTabLogin")
    .classList.toggle("active", _authMode === "login");
  document
    .getElementById("authTabRegister")
    .classList.toggle("active", _authMode === "register");
  setAuthError("");
}

/**
 * @returns {'login'|'register'}
 */
export function getAuthMode() {
  return _authMode;
}

export function openAuthModal(mode = "login") {
  switchAuthMode(mode);
  document.getElementById("authModal").classList.remove("hidden");
}

export function closeAuthModal() {
  document.getElementById("authModal").classList.add("hidden");
  setAuthError("");
}

export function setAuthError(message = "") {
  const el = document.getElementById("authError");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("hidden", !message);
}

// ============================================================================
// 弹窗：个人中心
// ============================================================================

/**
 * 打开个人中心面板并加载数据
 *
 * 先显示面板，再异步加载资料和历史记录。
 * 两个步骤解耦：面板立即打开（无等待感），数据异步填充。
 */
export function openProfilePanel() {
  document.getElementById("profilePanel").classList.remove("hidden");
  // 异步加载数据（延迟 import 避免循环依赖）
  import("./auth.js")
    .then((m) => m.loadProfileAndHistory())
    .catch((e) => console.error("加载个人中心失败:", e));
}

export function closeProfilePanel() {
  document.getElementById("profilePanel").classList.add("hidden");
}

/**
 * 渲染个人中心面板数据
 * @param {object} user
 * @param {{history_count:number}} summary
 */
export function renderProfile(user, summary, formatDateTime) {
  document.getElementById("profileUsername").textContent =
    user.username || "-";
  document.getElementById("profileMembership").textContent =
    user.membership_type === "member" ? "✨ 会员" : "普通用户";
  document.getElementById("profileCreatedAt").textContent =
    formatDateTime(user.created_at);
  document.getElementById("profileLastLogin").textContent =
    formatDateTime(user.last_login);
  document.getElementById("profileHistoryCount").textContent = String(
    summary.history_count || 0,
  );

  // 非会员显示升级提示
  if (user.membership_type !== "member") {
    const section = document.querySelector(".profile-section");
    if (section && !section.querySelector(".upgrade-hint")) {
      const hint = document.createElement("div");
      hint.className = "upgrade-hint";
      hint.style.cssText =
        "margin-top:12px;padding:12px;background:linear-gradient(135deg,#fef3c7,#fde68a);border-radius:10px;text-align:center";
      hint.innerHTML = `
        <div style="font-size:13px;color:#92400e;margin-bottom:8px">开通会员，获取详细医疗建议</div>
        <button class="upgrade-btn" onclick="window.UI.openUpgradeModal()">立即开通</button>`;
      section.appendChild(hint);
    }
  }
}

// ============================================================================
// 历史记录渲染
// ============================================================================

/**
 * 渲染历史记录列表
 * @param {Array} history
 * @param {(v:any)=>string} formatDateTime
 */
export function renderHistory(history, formatDateTime) {
  const listEl = document.getElementById("historyList");
  if (!Array.isArray(history) || history.length === 0) {
    listEl.innerHTML = '<div class="empty-state">暂无历史记录</div>';
    return;
  }
  listEl.innerHTML = history
    .map((item) => {
      const result = item?.triage_result?.message || "无结果";
      return `
        <div class="history-item">
          <div class="history-item-title">${escapeHtml(item.symptom_input || "未命名记录")}</div>
          <div class="history-item-meta">${escapeHtml(formatDateTime(item.created_at))}</div>
          <div class="history-item-result">${formatMessage(result)}</div>
        </div>`;
    })
    .join("");
}

// ============================================================================
// 弹窗：会员升级
// ============================================================================

export function openUpgradeModal(onSubmit) {
  const modal = document.createElement("div");
  modal.className = "modal-overlay";
  modal.id = "upgradeModal";
  modal.innerHTML = `
    <div class="auth-modal upgrade-modal">
      <div class="panel-header">
        <h3>✨ 开通会员</h3>
        <button class="icon-btn" onclick="window.UI.closeUpgradeModal()">✕</button>
      </div>
      <div class="upgrade-content">
        <div class="upgrade-benefits">
          <h4>会员专享权益</h4>
          <ul>
            <li>📊 详细疾病分析报告</li>
            <li>🩺 专业治疗建议</li>
            <li>🍽️ 个性化饮食指导</li>
            <li>💊 用药参考信息</li>
            <li>⏱️ 治疗周期预估</li>
            <li>💰 费用参考信息</li>
          </ul>
        </div>
        <div class="upgrade-price">
          <div class="price-tag">
            <span class="price-amount">¥29.9</span>
            <span class="price-period">/ 月</span>
          </div>
          <p class="price-note">模拟支付 - 点击立即开通</p>
        </div>
        <div class="upgrade-actions">
          <button class="primary-action-btn" id="upgradeSubmitBtn">立即开通</button>
          <button class="secondary-action-btn" onclick="window.UI.closeUpgradeModal()">稍后再说</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(modal);
  requestAnimationFrame(() => modal.classList.add("active"));

  // 绑定提交按钮
  const btn = document.getElementById("upgradeSubmitBtn");
  if (btn && onSubmit) {
    btn.addEventListener("click", onSubmit);
  }
}

export function closeUpgradeModal() {
  document.getElementById("upgradeModal")?.remove();
}

// ============================================================================
// 工具
// ============================================================================

/**
 * 格式化日期时间（本地化）
 * @param {string|number} value
 * @returns {string}
 */
export function formatDateTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("zh-CN");
}

/**
 * 格式化相对时间（刚刚 / X分钟前 / X小时前 / X天前 / 日期）
 * @param {string} dateStr - ISO 时间字符串
 * @returns {string}
 */
export function formatRelativeTime(dateStr) {
  if (!dateStr) return "-";
  const utc = dateStr.endsWith("Z") ? dateStr : dateStr + "Z";
  const date = new Date(utc);
  const diff = Math.floor((Date.now() - date) / 1000);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`;
  return date.toLocaleDateString("zh-CN");
}

/**
 * 统一错误信息提取
 * @param {*} error
 * @param {string} [fallback='操作失败，请稍后重试']
 * @returns {string}
 */
export function getErrorMessage(error, fallback = "操作失败，请稍后重试") {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  return error.error || error.message || fallback;
}

// ============================================================================
// 评论 UI（共享给 social 模块）
// ============================================================================

/**
 * 创建单条评论 DOM 元素
 * @param {object} comment
 * @returns {HTMLElement}
 */
export function createCommentElement(comment) {
  const div = document.createElement("div");
  div.className = "comment-item";
  div.dataset.id = comment.id;

  const isMember = comment.user?.membership_type === "member";
  const badge = isMember ? '<span class="member-badge-small">会员</span>' : "";

  div.innerHTML = `
    <div class="comment-header">
      <span class="comment-author">${escapeHtml(comment.user?.username || "匿名")}${badge}</span>
      <span class="comment-time">${formatRelativeTime(comment.created_at)}</span>
    </div>
    <div class="comment-content">${escapeHtml(comment.content)}</div>
    <div class="comment-actions">
      <button class="like-btn ${comment.is_liked ? "liked" : ""}" onclick="window.Social.toggleCommentLike(${comment.id}, this)">
        <span class="like-icon">👍</span>
        <span class="like-count">${comment.like_count || 0}</span>
      </button>
      <button class="reply-btn" onclick="window.Social.replyToComment(${comment.id}, '${escapeHtml(comment.user?.username || "匿名")}')">回复</button>
    </div>
    ${
      comment.replies?.length
        ? `
      <div class="comment-replies">
        ${comment.replies
          .map(
            (r) => `
          <div class="reply-item">
            <span class="reply-author">${escapeHtml(r.user?.username || "匿名")}:</span>
            <span class="reply-content">${escapeHtml(r.content)}</span>
          </div>`,
          )
          .join("")}
        ${comment.reply_count > 3 ? `<div class="more-replies" onclick="window.Social.loadReplies(${comment.id})">查看全部 ${comment.reply_count} 条回复</div>` : ""}
      </div>`
        : ""
    }`;
  return div;
}

// ============================================================================
// 评论弹窗（由 social 模块调用）
// ============================================================================

/**
 * 打开评论弹窗
 * @param {string} targetType - 'triage' | 'disease' | 'community'
 * @param {string} targetId
 * @param {string} title
 * @param {{onLoad:(append:boolean)=>Promise<void>, onSubmit:()=>Promise<void>, onClose:()=>void}} callbacks
 */
export function openCommentsModal(targetType, targetId, title, callbacks) {
  const modal = document.createElement("div");
  modal.className = "modal-overlay comments-modal-overlay";
  modal.id = "commentsModal";
  modal.innerHTML = `
    <div class="comments-modal">
      <div class="comments-modal-header">
        <h3>${escapeHtml(title)}</h3>
        <button class="icon-btn" id="commentsCloseBtn">✕</button>
      </div>
      <div class="comments-list" id="commentsList">
        <div class="loading-state">加载中...</div>
      </div>
      <div class="comments-input-area">
        <textarea id="commentInput" placeholder="写下你的评论..." rows="2"></textarea>
        <button class="send-btn" id="commentSendBtn">发送</button>
      </div>
    </div>`;
  document.body.appendChild(modal);
  requestAnimationFrame(() => modal.classList.add("active"));

  // 绑定事件
  document
    .getElementById("commentsCloseBtn")
    .addEventListener("click", () => closeCommentsModal(callbacks?.onClose));
  document
    .getElementById("commentSendBtn")
    .addEventListener("click", () => callbacks?.onSubmit?.());

  // 回车发送
  document.getElementById("commentInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      callbacks?.onSubmit?.();
    }
  });

  // 开始加载
  callbacks?.onLoad?.(false);
}

/**
 * 关闭评论弹窗
 */
export function closeCommentsModal(onClose) {
  document.getElementById("commentsModal")?.remove();
  onClose?.();
}
