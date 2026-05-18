/**
 * social.js — 社交互动（评论 + 点赞）
 *
 * 职责：
 *   1. 评论分页加载（GET /api/comments）
 *   2. 发表评论 / 回复评论（POST /api/comments）
 *   3. 点赞 / 取消点赞（POST/DELETE /api/likes）
 *   4. 加载评论回复列表（GET /api/comments/<id>/replies）
 *   5. 评论社区入口
 *
 * 注意：
 *   所有 DOM 创建委托给 ui.createCommentElement，
 *   弹窗管理委托给 ui.openCommentsModal / closeCommentsModal。
 *   本模块通过模块级变量管理待回复的父评论 ID，
 *   避免与 ui 模块的事件绑定发生冲突。
 *
 * @module social
 */

import {
  createCommentElement,
  openCommentsModal,
  closeCommentsModal,
  getErrorMessage,
} from "./ui.js";
import { authFetch } from "./auth.js";

// ============================================================================
// 状态
// ============================================================================

/** 当前评论目标 */
let currentCommentTarget = { type: null, id: null };

/** 评论分页 */
let commentsPagination = { page: 1, hasMore: true, loading: false };

/**
 * 待回复的父评论 ID（null 表示顶层评论）
 *
 * 当用户点击"回复"时设置此值，下次提交评论时会携带 parent_id。
 * 提交成功后自动重置为 null。
 */
let pendingReplyId = null;

// ============================================================================
// 评论社区入口
// ============================================================================

export function openCommentsCommunity() {
  currentCommentTarget = { type: "community", id: "general" };
  resetPagination();

  openCommentsModal("community", "general", "💬 评论社区", {
    onLoad: (append) => _loadComments(append),
    onSubmit: () => _handleSubmit(),
    onClose: () => _cleanup(),
  });
}

// ============================================================================
// 评论弹窗（供完成卡片按钮调用）
// ============================================================================

/**
 * 打开指定目标的评论弹窗
 *
 * @param {string} targetType - 'triage' | 'disease' | 'community'
 * @param {string} targetId
 * @param {string} [title='评论']
 */
export function openCommentsModalFor(targetType, targetId, title = "评论") {
  currentCommentTarget = { type: targetType, id: targetId };
  resetPagination();

  openCommentsModal(targetType, targetId, title, {
    onLoad: (append) => _loadComments(append),
    onSubmit: () => _handleSubmit(),
    onClose: () => _cleanup(),
  });
}

export function closeCommentsModalExternal() {
  _cleanup();
}

// ============================================================================
// 辅助
// ============================================================================

function resetPagination() {
  commentsPagination = { page: 1, hasMore: true, loading: false };
  pendingReplyId = null;
}

function _cleanup() {
  currentCommentTarget = { type: null, id: null };
  pendingReplyId = null;
}

// ============================================================================
// 评论加载
// ============================================================================

/**
 * 加载评论列表
 *
 * @param {boolean} append - true=追加模式（"加载更多"）
 */
async function _loadComments(append = false) {
  if (commentsPagination.loading) return;
  if (!append && !commentsPagination.hasMore) return;

  const { type, id } = currentCommentTarget;
  if (!type || !id) return;

  commentsPagination.loading = true;
  const listEl = document.getElementById("commentsList");

  if (!append) listEl.innerHTML = '<div class="loading-state">加载中...</div>';

  try {
    const params = new URLSearchParams({
      target_type: type,
      target_id: id,
      page: String(commentsPagination.page),
      limit: "20",
      sort: "hot",
    });
    const data = await authFetch(`/api/comments?${params}`);

    commentsPagination.hasMore = data.has_more;
    if (!append) listEl.innerHTML = "";

    if (data.items.length === 0 && !append) {
      listEl.innerHTML = '<div class="empty-state">暂无评论，来写第一条吧~</div>';
      return;
    }

    listEl.querySelector(".load-more-btn")?.remove();

    for (const comment of data.items) {
      listEl.appendChild(createCommentElement(comment));
    }

    if (data.has_more) {
      const btn = document.createElement("button");
      btn.className = "load-more-btn";
      btn.textContent = "加载更多";
      btn.addEventListener("click", () => {
        commentsPagination.page++;
        _loadComments(true);
      });
      listEl.appendChild(btn);
    }
  } catch (err) {
    console.error("[social] 加载评论失败:", err);
    if (!append) listEl.innerHTML = '<div class="empty-state">加载失败，请重试</div>';
  } finally {
    commentsPagination.loading = false;
  }
}

// ============================================================================
// 发表 / 回复
// ============================================================================

/**
 * 统一提交入口
 *
 * 若 pendingReplyId 不为 null，则作为父评论回复提交，
 * 提交后自动清除 pendingReplyId。
 */
async function _handleSubmit() {
  const { type, id } = currentCommentTarget;
  if (!type || !id) return;

  const input = document.getElementById("commentInput");
  const content = (input?.value || "").trim();

  if (!content) {
    alert("请输入评论内容");
    return;
  }
  if (content.length > 500) {
    alert("评论内容不能超过 500 个字符");
    return;
  }

  try {
    const body = {
      target_type: type,
      target_id: id,
      content,
    };
    if (pendingReplyId) {
      body.parent_id = pendingReplyId;
    }

    await authFetch("/api/comments", {
      method: "POST",
      body: JSON.stringify(body),
    });

    // 提交成功，清空输入框和回复状态
    input.value = "";
    pendingReplyId = null;
    commentsPagination.page = 1;
    await _loadComments(false);
  } catch (err) {
    alert(getErrorMessage(err, "评论失败"));
  }
}

// ============================================================================
// 回复评论
// ============================================================================

/**
 * 回复指定评论
 *
 * 在输入框中填入 @用户名 前缀，并设置 pendingReplyId。
 * 用户点击发送时，_handleSubmit 会自动携带 parent_id。
 *
 * @param {number} commentId - 父评论 ID
 * @param {string} username  - 被回复用户名
 */
export function replyToComment(commentId, username) {
  pendingReplyId = commentId;

  const input = document.getElementById("commentInput");
  if (input) {
    input.value = `@${username} `;
    input.focus();
  }
}

// ============================================================================
// 点赞
// ============================================================================

/**
 * 切换评论点赞状态（乐观更新 UI）
 *
 * @param {number} commentId
 * @param {HTMLElement} btn - 点赞按钮元素
 */
export async function toggleCommentLike(commentId, btn) {
  const isLiked = btn.classList.contains("liked");
  const countEl = btn.querySelector(".like-count");
  let count = parseInt(countEl.textContent) || 0;

  // 乐观更新
  btn.classList.toggle("liked");
  countEl.textContent = isLiked ? count - 1 : count + 1;

  try {
    if (isLiked) {
      await authFetch("/api/likes", {
        method: "DELETE",
        body: JSON.stringify({
          target_type: "comment",
          target_id: String(commentId),
        }),
      });
    } else {
      await authFetch("/api/likes", {
        method: "POST",
        body: JSON.stringify({
          target_type: "comment",
          target_id: String(commentId),
        }),
      });
    }
  } catch {
    // 失败时回滚
    btn.classList.toggle("liked");
    countEl.textContent = isLiked ? count : count - 1;
    console.error("[social] 点赞操作失败");
  }
}

// ============================================================================
// 加载回复
// ============================================================================

/**
 * 展开某条评论的完整回复列表
 *
 * @param {number} commentId
 */
export async function loadReplies(commentId) {
  try {
    const data = await authFetch(
      `/api/comments/${commentId}/replies?page=1&limit=50`,
    );
    const commentEl = document.querySelector(
      `.comment-item[data-id="${commentId}"]`,
    );
    if (!commentEl) return;

    const container = commentEl.querySelector(".comment-replies");
    if (container) {
      container.innerHTML = data.items
        .map(
          (r) => `
          <div class="reply-item">
            <span class="reply-author">${_esc(r.user?.username || "匿名")}:</span>
            <span class="reply-content">${_esc(r.content)}</span>
          </div>`,
        )
        .join("");
    }
  } catch (err) {
    console.error("[social] 加载回复失败:", err);
  }
}

// ============================================================================
// 本地工具（避免循环依赖 ui）
// ============================================================================

function _esc(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
