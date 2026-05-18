/**
 * app.js — 轻量入口文件
 *
 * 原来的单体 app.js 已拆分到 js/ 目录：
 *   - js/core.js   : 全局配置、共享状态、HTTP 基础设施
 *   - js/ui.js     : DOM 渲染、弹窗、消息气泡、工具函数
 *   - js/auth.js   : 登录、注册、登出、个人中心、会员升级
 *   - js/chat.js   : 导诊对话、欢迎语、重置会话
 *   - js/social.js : 评论、回复、点赞、评论社区
 *   - js/app.js    : 模块装配与事件绑定
 *
 * 保留本文件作为稳定入口，避免 index.html 或 Capacitor 配置引用失效。
 */
import './js/app.js';
