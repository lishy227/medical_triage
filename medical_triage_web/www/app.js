/**
 * 医疗导诊系统前端主逻辑
 * 
 * 功能模块：
 * 1. 服务器重启检测 - 检测后端重启并自动退出登录
 * 2. 用户认证 - 登录、注册、Token管理
 * 3. 导诊对话 - 与后端API交互完成症状导诊
 * 4. 会员系统 - 会员升级、详细建议展示
 * 5. 个人中心 - 用户信息、历史记录
 * 
 * 技术栈：
 * - 原生JavaScript (ES6+)
 * - Fetch API (支持Capacitor HTTP插件)
 * - LocalStorage 存储Token
 */

// ==================== 全局配置 ====================

/**
 * API基础URL配置
 * 修改此变量可切换服务器地址
 * - 本地开发: http://localhost:5001
 * - 阿里云服务器: http://47.107.108.157:5001
 */
const API_BASE = "http://localhost:5001";

// ==================== Capacitor支持 ====================

/**
 * Capacitor HTTP插件检测
 * 用于检测是否在Capacitor混合应用环境中运行
 * 如果存在，使用原生HTTP请求替代fetch（避免CORS问题）
 */
let CapacitorHttp = null;
if (typeof window !== 'undefined' && window.Capacitor) {
    CapacitorHttp = window.Capacitor.Plugins.Http;
}

// ==================== 应用状态 ====================

/** 当前会话ID，用于区分不同的导诊对话 */
let sessionId = generateSessionId();

/** 是否正在等待后端响应，用于防止重复提交 */
let isWaiting = false;

/** 当前导诊阶段（0-3） */
let currentStage = 0;

// ==================== 服务器重启检测 ====================

/** localStorage键名，存储服务器实例ID */
const SERVER_INSTANCE_KEY = 'server_instance_id';

/** 服务器状态检测间隔（毫秒），默认30秒 */
const SERVER_CHECK_INTERVAL = 30000;

/**
 * 检查服务器是否重启
 * 
 * 通过比较localStorage中存储的实例ID与后端返回的当前实例ID，
 * 判断服务器是否重启。如果重启，需要重新登录。
 * 
 * @returns {Promise<boolean>} true表示服务器已重启，false表示未重启
 */
async function checkServerRestart() {
    try {
        const response = await fetch(`${API_BASE}/api/server/info`);
        const data = await response.json();
        
        const storedInstanceId = localStorage.getItem(SERVER_INSTANCE_KEY);
        const currentInstanceId = data.instance_id;
        
        if (!storedInstanceId) {
            // 第一次访问，保存实例ID
            localStorage.setItem(SERVER_INSTANCE_KEY, currentInstanceId);
            return false;
        }
        
        if (storedInstanceId !== currentInstanceId) {
            // 服务器已重启
            console.log('检测到服务器重启，自动退出登录');
            localStorage.setItem(SERVER_INSTANCE_KEY, currentInstanceId);
            return true;
        }
        
        return false;
    } catch (error) {
        console.error('检查服务器状态失败:', error);
        return false;
    }
}

/**
 * 执行自动退出登录
 * 
 * 清除本地存储的Token和用户信息，显示提示消息，
 * 然后刷新页面以清除所有状态。
 */
function autoLogout() {
    const hadUser = getStoredToken();
    setStoredToken('');
    setCurrentUser(null);
    
    if (hadUser) {
        // 显示提示消息
        addSystemMessage('服务器已重启，请重新登录。');
        // 刷新页面以清除状态
        setTimeout(() => {
            window.location.reload();
        }, 1500);
    }
}

/**
 * 启动服务器状态检测
 * 
 * 页面加载时立即检查一次，然后定期（30秒）检查服务器状态。
 * 如果检测到服务器重启，自动执行退出登录。
 */
function startServerCheck() {
    // 立即检查一次
    checkServerRestart().then(isRestarted => {
        if (isRestarted) {
            autoLogout();
        }
    });
    
    // 定期检测
    setInterval(async () => {
        const isRestarted = await checkServerRestart();
        if (isRestarted) {
            autoLogout();
        }
    }, SERVER_CHECK_INTERVAL);
}

function getAuthToken() {
    try {
        return localStorage.getItem('auth_token') || '';
    } catch (error) {
        console.warn('读取登录令牌失败:', error);
        return '';
    }
}

function buildAuthHeaders(extraHeaders = {}) {
    const token = getAuthToken();
    return token
        ? { ...extraHeaders, Authorization: `Bearer ${token}` }
        : extraHeaders;
}

// 生成会话ID
function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// DOM元素
const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const loadingOverlay = document.getElementById('loading');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadWelcomeMessage();
    userInput.focus();
});

// 统一的 HTTP 请求函数
async function httpRequest(url, options = {}) {
    // 如果在 Capacitor 环境中，使用原生 HTTP
    if (CapacitorHttp) {
        const response = await CapacitorHttp.request({
            url: url,
            method: options.method || 'GET',
            headers: options.headers || {},
            data: options.body ? JSON.parse(options.body) : undefined
        });
        return { json: () => Promise.resolve(response.data) };
    }
    // 否则使用标准 fetch
    return fetch(url, options);
}

// 加载欢迎消息
async function loadWelcomeMessage() {
    try {
        showLoading();
        const response = await httpRequest(`${API_BASE}/api/welcome?session_id=${sessionId}`, {
            headers: buildAuthHeaders()
        });
        const data = await response.json();
        
        // 更新欢迎消息
        const welcomeBubble = document.querySelector('.system-message .message-bubble');
        if (welcomeBubble && data.message) {
            welcomeBubble.innerHTML = `<p>${escapeHtml(data.message)}</p>`;
        }
    } catch (error) {
        console.error('加载欢迎消息失败:', error);
    } finally {
        hideLoading();
    }
}

// 发送消息
async function sendMessage() {
    const message = userInput.value.trim();
    if (!message || isWaiting) return;

    // 添加用户消息
    addUserMessage(message);
    userInput.value = '';
    userInput.style.height = 'auto';
    
    // 显示加载状态
    isWaiting = true;
    sendBtn.disabled = true;
    const typingId = addTypingIndicator();

    try {
        const response = await httpRequest(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: buildAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        const data = await response.json();
        
        // 移除打字指示器
        removeTypingIndicator(typingId);
        
        if (data.error) {
            addBotMessage('抱歉，出现了错误：' + data.error);
        } else {
            // 更新阶段
            if (data.stage !== undefined) {
                updateStage(data.stage);
            }
            
            // 显示回复
            if (data.is_complete) {
                addCompleteMessage(data.message, data.records, data);
            } else {
                addBotMessage(data.message);
            }
        }
    } catch (error) {
        removeTypingIndicator(typingId);
        addBotMessage('抱歉，网络连接出现问题，请稍后重试。');
        console.error('发送消息失败:', error);
    } finally {
        isWaiting = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
}

// 重置对话
async function resetChat() {
    if (isWaiting) return;
    
    showLoading();
    
    try {
        const response = await httpRequest(`${API_BASE}/api/reset`, {
            method: 'POST',
            headers: buildAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ session_id: sessionId })
        });

        const data = await response.json();
        
        // 清空消息区域
        messagesContainer.innerHTML = '';
        
        // 添加新的欢迎消息
        addSystemMessage(data.message);
        
        // 重置阶段
        updateStage(0);
        
    } catch (error) {
        console.error('重置失败:', error);
        addBotMessage('重置失败，请刷新页面重试。');
    } finally {
        hideLoading();
        userInput.focus();
    }
}

// 添加用户消息
function addUserMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user-message';
    messageDiv.innerHTML = `
        <div class="message-avatar">👤</div>
        <div class="message-content">
            <div class="message-bubble">${escapeHtml(text)}</div>
            <div class="message-time">${getCurrentTime()}</div>
        </div>
    `;
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
}

// 添加系统消息
function addSystemMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system-message';
    messageDiv.innerHTML = `
        <div class="message-avatar">🏥</div>
        <div class="message-content">
            <div class="message-bubble">${formatMessage(text)}</div>
            <div class="message-time">${getCurrentTime()}</div>
        </div>
    `;
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
}

// 添加机器人消息
function addBotMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot-message';
    messageDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="message-bubble">${formatMessage(text)}</div>
            <div class="message-time">${getCurrentTime()}</div>
        </div>
    `;
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
}

// 渲染详细建议（会员专享）
function renderDetailedAdvice(advice) {
    if (!advice || typeof advice !== 'object') return '';
    
    let html = '<div class="detailed-advice">';
    
    // 可能的疾病
    if (advice.possible_diseases && advice.possible_diseases.length > 0) {
        html += '<div class="advice-section"><h4>🔍 可能的相关疾病</h4>';
        advice.possible_diseases.forEach((disease, index) => {
            html += `
                <div class="disease-card">
                    <div class="disease-name">${index + 1}. ${escapeHtml(disease.name)}</div>
                    <div class="disease-desc">${escapeHtml(disease.description)}</div>
                    ${disease.symptoms && disease.symptoms.length > 0 ? 
                        `<div class="disease-symptoms"><strong>症状：</strong>${disease.symptoms.map(s => escapeHtml(s)).join('、')}</div>` : ''}
                    ${disease.cure_way && disease.cure_way.length > 0 ? 
                        `<div class="disease-cure"><strong>治疗方式：</strong>${disease.cure_way.map(c => escapeHtml(c)).join('、')}</div>` : ''}
                    ${disease.cure_lasttime ? `<div class="disease-duration"><strong>治疗周期：</strong>${escapeHtml(disease.cure_lasttime)}</div>` : ''}
                    ${disease.cured_prob ? `<div class="disease-rate"><strong>治愈率：</strong>${escapeHtml(disease.cured_prob)}</div>` : ''}
                    ${disease.cost_money ? `<div class="disease-cost"><strong>参考费用：</strong>${escapeHtml(disease.cost_money)}</div>` : ''}
                </div>
            `;
        });
        html += '</div>';
    }
    
    // 饮食建议
    if (advice.diet_suggestions) {
        html += '<div class="advice-section"><h4>🍽️ 饮食建议</h4>';
        if (advice.diet_suggestions.recommended && advice.diet_suggestions.recommended.length > 0) {
            html += `<div class="diet-recommended"><strong>推荐食用：</strong>${advice.diet_suggestions.recommended.map(d => escapeHtml(d)).join('、')}</div>`;
        }
        if (advice.diet_suggestions.avoid && advice.diet_suggestions.avoid.length > 0) {
            html += `<div class="diet-avoid"><strong>建议避免：</strong>${advice.diet_suggestions.avoid.map(d => escapeHtml(d)).join('、')}</div>`;
        }
        html += '</div>';
    }
    
    // 通用建议
    if (advice.general_tips && advice.general_tips.length > 0) {
        html += '<div class="advice-section"><h4>💡 就医建议</h4><ul class="tips-list">';
        advice.general_tips.forEach(tip => {
            html += `<li>${escapeHtml(tip)}</li>`;
        });
        html += '</ul></div>';
    }
    
    html += '</div>';
    return html;
}

// 添加完成消息（带结果卡片）
function addCompleteMessage(text, records, result = {}) {
    const departments = Array.isArray(result.departments) && result.departments.length
        ? result.departments
        : extractDepartmentsFromText(text);

    const recommendedDepartment = result.recommended_department || departments[0] || '暂无推荐';
    const detailLocked = !!result.detail_locked;
    const detailedAdvice = result.detailed_medical_advice || '';
    const conversationSummary = result.conversation_summary || '';
    const detailLevel = result.detail_level || (detailLocked ? 'basic' : 'member');

    const lines = String(text || '').split('\n');
    let mainMessage = '';

    for (const line of lines) {
        if (line.includes('最终推荐结果:')) {
            continue;
        }
        if (!line.includes('收集信息:')) {
            mainMessage += line + '\n';
        }
    }

    const detailBlock = detailLocked
        ? `
            <div class="member-lock-box">
                <div class="member-lock-title">🔒 详细建议为会员专享内容</div>
                <div class="member-lock-text">当前仅展示推荐科室。开通会员后，可查看完整疾病分析、治疗建议、饮食指导等详细内容。</div>
                <button class="upgrade-btn" onclick="openUpgradeModal()">✨ 立即开通会员</button>
            </div>
        `
        : (detailedAdvice
            ? renderDetailedAdvice(detailedAdvice)
            : '');

    const summaryBlock = conversationSummary
        ? `
            <div class="summary-text">问诊摘要：${escapeHtml(conversationSummary)}</div>
        `
        : '';

    const badgeText = detailLevel === 'member' ? '会员详细版' : '基础版';
    const badgeClass = detailLevel === 'member' ? 'detail-badge member' : 'detail-badge basic';

    // 生成唯一的会话ID用于评论
    const commentTargetId = sessionId || 'default';

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot-message';
    messageDiv.innerHTML = `
        <div class="message-avatar">🎉</div>
        <div class="message-content">
            <div class="message-bubble">
                <p>${formatMessage(mainMessage.trim() || text || '')}</p>
                <div class="result-card">
                    <div class="result-card-header">
                        <h3>🏥 推荐就诊科室</h3>
                        <span class="${badgeClass}">${badgeText}</span>
                    </div>
                    <div class="departments">
                        ${departments.map(d => `<span class="dept-tag">${escapeHtml(d)}</span>`).join('') || `<span class="dept-tag">${escapeHtml(recommendedDepartment)}</span>`}
                    </div>
                    ${summaryBlock}
                    ${detailBlock}
                    <div class="result-actions">
                        <button class="comment-trigger-btn" onclick="openCommentsModal('triage', '${commentTargetId}', '导诊评论')">
                            💬 评论
                        </button>
                    </div>
                </div>
            </div>
            <div class="message-time">${getCurrentTime()}</div>
        </div>
    `;
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
}

function extractDepartmentsFromText(text) {
    const match = String(text || '').match(/最终推荐结果:\s*\[(.*?)\]/);
    if (!match || !match[1]) {
        return [];
    }
    return match[1].split(',').map(d => d.trim().replace(/['"]/g, '')).filter(Boolean);
}

// 添加打字指示器
function addTypingIndicator() {
    const id = 'typing-' + Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot-message';
    messageDiv.id = id;
    messageDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
    return id;
}

// 移除打字指示器
function removeTypingIndicator(id) {
    const element = document.getElementById(id);
    if (element) {
        element.remove();
    }
}

// 更新阶段指示器
function updateStage(stage) {
    currentStage = stage;
    const steps = document.querySelectorAll('.step');
    
    steps.forEach((step, index) => {
        step.classList.remove('active', 'completed');
        if (index < stage) {
            step.classList.add('completed');
            step.querySelector('.step-num').textContent = '✓';
        } else if (index === stage) {
            step.classList.add('active');
            step.querySelector('.step-num').textContent = (index + 1).toString();
        } else {
            step.querySelector('.step-num').textContent = (index + 1).toString();
        }
    });
}

// 格式化消息（处理换行和列表）
function formatMessage(text) {
    if (!text) return '';
    
    // 转义HTML
    let formatted = escapeHtml(text);
    
    // 处理换行
    formatted = formatted.replace(/\n/g, '</p><p>');
    
    // 包裹在p标签中
    if (!formatted.startsWith('<p>')) {
        formatted = '<p>' + formatted;
    }
    if (!formatted.endsWith('</p>')) {
        formatted = formatted + '</p>';
    }
    
    return formatted;
}

// 转义HTML特殊字符
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 获取当前时间
function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
}

// 滚动到底部
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// 处理键盘事件
function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// 显示加载
function showLoading() {
    loadingOverlay.classList.add('active');
}

// 隐藏加载
function hideLoading() {
    loadingOverlay.classList.remove('active');
}

// 自动调整输入框高度
userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

let authMode = 'login';
let currentUser = null;

function getStoredToken() {
    return localStorage.getItem('auth_token') || '';
}

function setStoredToken(token) {
    if (token) {
        localStorage.setItem('auth_token', token);
    } else {
        localStorage.removeItem('auth_token');
    }
}

function setCurrentUser(user) {
    currentUser = user || null;
    updateAuthUI();
}

function formatDateTime(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN');
}

function getErrorMessage(error, fallback = '操作失败，请稍后重试') {
    if (!error) return fallback;
    if (typeof error === 'string') return error;
    return error.error || error.message || fallback;
}

function setAuthError(message = '') {
    const el = document.getElementById('authError');
    if (!el) return;
    if (message) {
        el.textContent = message;
        el.classList.remove('hidden');
    } else {
        el.textContent = '';
        el.classList.add('hidden');
    }
}

function switchAuthMode(mode) {
    authMode = mode === 'register' ? 'register' : 'login';
    document.getElementById('authModalTitle').textContent = authMode === 'register' ? '注册' : '登录';
    document.getElementById('authSubmitBtn').textContent = authMode === 'register' ? '注册' : '登录';
    document.getElementById('authTabLogin').classList.toggle('active', authMode === 'login');
    document.getElementById('authTabRegister').classList.toggle('active', authMode === 'register');
    setAuthError('');
}

function openAuthModal(mode = 'login') {
    switchAuthMode(mode);
    document.getElementById('authModal').classList.remove('hidden');
}

function closeAuthModal() {
    document.getElementById('authModal').classList.add('hidden');
    setAuthError('');
}

function openProfilePanel() {
    document.getElementById('profilePanel').classList.remove('hidden');
    loadProfileAndHistory();
}

function closeProfilePanel() {
    document.getElementById('profilePanel').classList.add('hidden');
}

async function authFetch(path, options = {}) {
    const token = getStoredToken();
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };

    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }

    const url = `${API_BASE}${path}`;
    
    let response;
    try {
        response = await fetch(url, {
            ...options,
            headers,
        });
    } catch (networkError) {
        console.error('网络请求失败:', networkError);
        throw {
            error: `无法连接到服务器，请检查网络或稍后重试`,
            details: String(networkError)
        };
    }

    let data = {};
    try {
        data = await response.json();
    } catch (_) {
        data = {};
    }

    if (!response.ok) {
        if (response.status === 401) {
            setStoredToken('');
            setCurrentUser(null);
        }
        // 优先使用服务器返回的错误信息
        throw data.error ? data : { error: `服务器错误 (${response.status})` };
    }

    return data;
}

function updateAuthUI() {
    const user = currentUser;
    const isMember = user && user.membership_type === 'member';
    const statusText = user 
        ? (isMember ? `✨ 会员：${user.username}` : `已登录：${user.username}`)
        : '未登录';
    document.getElementById('authStatusText').textContent = statusText;
    document.getElementById('loginBtn').classList.toggle('hidden', !!user);
    document.getElementById('registerBtn').classList.toggle('hidden', !!user);
    document.getElementById('profileBtn').classList.toggle('hidden', !user);
    document.getElementById('logoutBtn').classList.toggle('hidden', !user);
}

async function submitAuthForm(event) {
    event.preventDefault();
    setAuthError('');

    const username = document.getElementById('authUsername').value.trim();
    const password = document.getElementById('authPassword').value;

    if (!username || !password) {
        setAuthError('用户名和密码不能为空');
        return;
    }

    try {
        showLoading();
        const path = authMode === 'register' ? '/api/auth/register' : '/api/auth/login';
        console.log(`正在请求: ${API_BASE}${path}`, { username, password: '***' });
        
        const data = await authFetch(path, {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });

        console.log('登录/注册成功:', data);
        setStoredToken(data.token || '');
        setCurrentUser(data.user || null);
        closeAuthModal();
        document.getElementById('authUsername').value = '';
        document.getElementById('authPassword').value = '';
        addSystemMessage(data.message || (authMode === 'register' ? '注册成功' : '登录成功'));

        try {
            await loadWelcomeMessage();
        } catch (_) {
            // 忽略欢迎语加载失败，避免打断登录主流程
        }
    } catch (error) {
        console.error('登录/注册失败:', error);
        setAuthError(getErrorMessage(error));
    } finally {
        hideLoading();
    }
}

async function logout() {
    try {
        showLoading();
        await authFetch('/api/auth/logout', { method: 'POST' });
    } catch (_) {
        // 即使后端登出失败，也清本地态
    } finally {
        setStoredToken('');
        setCurrentUser(null);
        closeProfilePanel();
        hideLoading();
        addSystemMessage('您已退出登录');
    }
}

async function loadProfile() {
    const data = await authFetch('/api/user/center');
    const user = data.user || {};
    const summary = data.summary || {};
    setCurrentUser(user);

    document.getElementById('profileUsername').textContent = user.username || '-';
    
    // 显示会员状态
    const membershipText = user.membership_type === 'member' ? '✨ 会员' : '普通用户';
    document.getElementById('profileMembership').textContent = membershipText;
    
    document.getElementById('profileCreatedAt').textContent = formatDateTime(user.created_at);
    document.getElementById('profileLastLogin').textContent = formatDateTime(user.last_login);
    document.getElementById('profileHistoryCount').textContent = String(summary.history_count || 0);
    
    // 如果用户不是会员，显示升级提示
    if (user.membership_type !== 'member') {
        const profileSection = document.querySelector('.profile-section');
        if (profileSection && !profileSection.querySelector('.upgrade-hint')) {
            const upgradeHint = document.createElement('div');
            upgradeHint.className = 'upgrade-hint';
            upgradeHint.style.cssText = 'margin-top: 12px; padding: 12px; background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-radius: 10px; text-align: center;';
            upgradeHint.innerHTML = `
                <div style="font-size: 13px; color: #92400e; margin-bottom: 8px;">开通会员，获取详细医疗建议</div>
                <button class="upgrade-btn" onclick="openUpgradeModal()">立即开通</button>
            `;
            profileSection.appendChild(upgradeHint);
        }
    }
}

function renderHistory(history) {
    const listEl = document.getElementById('historyList');
    if (!Array.isArray(history) || history.length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无历史记录</div>';
        return;
    }

    listEl.innerHTML = history.map(item => {
        const result = item?.triage_result?.message || '无结果';
        return `
            <div class="history-item">
                <div class="history-item-title">${escapeHtml(item.symptom_input || '未命名记录')}</div>
                <div class="history-item-meta">${escapeHtml(formatDateTime(item.created_at))}</div>
                <div class="history-item-result">${formatMessage(result)}</div>
            </div>
        `;
    }).join('');
}

async function loadHistory(silent = false) {
    try {
        const data = await authFetch('/api/user/history');
        renderHistory(data.history || []);
        if (typeof data.count === 'number') {
            document.getElementById('profileHistoryCount').textContent = String(data.count);
        }
    } catch (error) {
        if (!silent) {
            addSystemMessage(getErrorMessage(error, '加载历史记录失败'));
        }
        throw error;
    }
}

async function loadProfileAndHistory() {
    try {
        showLoading();
        await loadProfile();
        await loadHistory(true);
    } catch (error) {
        addSystemMessage(getErrorMessage(error, '加载个人中心失败'));
    } finally {
        hideLoading();
    }
}

async function bootstrapAuth() {
    const token = getStoredToken();
    setStoredToken(token);
    if (!token) {
        setCurrentUser(null);
        updateAuthUI();
        return;
    }

    try {
        const data = await authFetch('/api/auth/profile');
        setCurrentUser(data.user || null);
    } catch (_) {
        setStoredToken('');
        setCurrentUser(null);
    }
}

const originalLoadWelcomeMessage = loadWelcomeMessage;
loadWelcomeMessage = async function () {
    if (!getStoredToken()) {
        return;
    }
    return originalLoadWelcomeMessage();
};

const originalSendMessage = sendMessage;
sendMessage = async function () {
    if (!getStoredToken()) {
        openAuthModal('login');
        addSystemMessage('请先登录，再开始导诊。');
        return;
    }
    return originalSendMessage();
};

const originalResetChat = resetChat;
resetChat = async function () {
    if (!getStoredToken()) {
        messagesContainer.innerHTML = '';
        addSystemMessage('请先登录，再开始新的导诊会话。');
        return;
    }
    return originalResetChat();
};

// 会员升级相关功能
function openUpgradeModal() {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'upgradeModal';
    modal.innerHTML = `
        <div class="auth-modal upgrade-modal">
            <div class="panel-header">
                <h3>✨ 开通会员</h3>
                <button class="icon-btn" onclick="closeUpgradeModal()">✕</button>
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
                    <button class="primary-action-btn" onclick="submitUpgrade()">立即开通</button>
                    <button class="secondary-action-btn" onclick="closeUpgradeModal()">稍后再说</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    // 触发重绘以显示动画
    requestAnimationFrame(() => modal.classList.add('active'));
}

function closeUpgradeModal() {
    const modal = document.getElementById('upgradeModal');
    if (modal) {
        modal.remove();
    }
}

async function submitUpgrade() {
    try {
        showLoading();
        const data = await authFetch('/api/membership/upgrade', {
            method: 'POST'
        });
        
        // 更新当前用户信息
        setCurrentUser(data.user || null);
        closeUpgradeModal();
        addSystemMessage('🎉 ' + (data.message || '会员升级成功！现在您可以享受详细的医疗建议服务。'));
        
        // 刷新个人中心显示
        updateAuthUI();
    } catch (error) {
        console.error('升级失败:', error);
        alert(getErrorMessage(error, '升级失败，请稍后重试'));
    } finally {
        hideLoading();
    }
}

async function checkMembershipStatus() {
    try {
        const data = await authFetch('/api/membership/status');
        return data;
    } catch (error) {
        console.error('获取会员状态失败:', error);
        return null;
    }
}

window.openAuthModal = openAuthModal;
window.closeAuthModal = closeAuthModal;
window.switchAuthMode = switchAuthMode;
window.submitAuthForm = submitAuthForm;
window.openProfilePanel = openProfilePanel;
window.closeProfilePanel = closeProfilePanel;
window.logout = logout;
window.loadHistory = loadHistory;
window.openUpgradeModal = openUpgradeModal;
window.closeUpgradeModal = closeUpgradeModal;
window.submitUpgrade = submitUpgrade;
window.checkServerRestart = checkServerRestart;
window.startServerCheck = startServerCheck;

// ==================== 社交互动功能（评论、点赞）====================

/** 当前评论目标信息 */
let currentCommentTarget = { type: null, id: null };

/** 评论分页状态 */
let commentsPagination = { page: 1, hasMore: true, loading: false };

/**
 * 打开评论社区（查看所有评论）
 * 这是一个常驻功能，不依赖特定导诊会话
 */
function openCommentsCommunity() {
    // 使用一个特殊的社区目标
    openCommentsModal('community', 'general', '💬 评论社区');
}

/**
 * 打开评论弹窗
 * @param {string} targetType - 目标类型（'triage'/'disease'/'community'）
 * @param {string} targetId - 目标ID
 * @param {string} title - 弹窗标题
 */
function openCommentsModal(targetType, targetId, title = '评论') {
    currentCommentTarget = { type: targetType, id: targetId };
    commentsPagination = { page: 1, hasMore: true, loading: false };
    
    // 创建弹窗
    const modal = document.createElement('div');
    modal.className = 'modal-overlay comments-modal-overlay';
    modal.id = 'commentsModal';
    modal.innerHTML = `
        <div class="comments-modal">
            <div class="comments-modal-header">
                <h3>${escapeHtml(title)}</h3>
                <button class="icon-btn" onclick="closeCommentsModal()">✕</button>
            </div>
            <div class="comments-list" id="commentsList">
                <div class="loading-state">加载中...</div>
            </div>
            <div class="comments-input-area">
                <textarea id="commentInput" placeholder="写下你的评论..." rows="2"></textarea>
                <button class="send-btn" onclick="submitComment()">发送</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('active'));
    
    // 加载评论列表
    loadComments();
}

/**
 * 关闭评论弹窗
 */
function closeCommentsModal() {
    const modal = document.getElementById('commentsModal');
    if (modal) {
        modal.remove();
    }
    currentCommentTarget = { type: null, id: null };
}

/**
 * 加载评论列表
 * @param {boolean} append - 是否追加模式（加载更多）
 */
async function loadComments(append = false) {
    if (commentsPagination.loading || (!append && !commentsPagination.hasMore)) return;
    
    const { type, id } = currentCommentTarget;
    if (!type || !id) return;
    
    commentsPagination.loading = true;
    const listEl = document.getElementById('commentsList');
    
    if (!append) {
        listEl.innerHTML = '<div class="loading-state">加载中...</div>';
    }
    
    try {
        const data = await authFetch(`/api/comments?target_type=${type}&target_id=${id}&page=${commentsPagination.page}&limit=20&sort=hot`);
        
        commentsPagination.hasMore = data.has_more;
        
        if (!append) {
            listEl.innerHTML = '';
        }
        
        if (data.items.length === 0 && !append) {
            listEl.innerHTML = '<div class="empty-state">暂无评论，来写第一条吧~</div>';
            return;
        }
        
        // 移除加载更多按钮
        const loadMoreBtn = listEl.querySelector('.load-more-btn');
        if (loadMoreBtn) loadMoreBtn.remove();
        
        // 渲染评论
        data.items.forEach(comment => {
            const commentEl = createCommentElement(comment);
            listEl.appendChild(commentEl);
        });
        
        // 添加加载更多按钮
        if (data.has_more) {
            const btn = document.createElement('button');
            btn.className = 'load-more-btn';
            btn.textContent = '加载更多';
            btn.onclick = () => {
                commentsPagination.page++;
                loadComments(true);
            };
            listEl.appendChild(btn);
        }
    } catch (error) {
        console.error('加载评论失败:', error);
        if (!append) {
            listEl.innerHTML = '<div class="empty-state">加载失败，请重试</div>';
        }
    } finally {
        commentsPagination.loading = false;
    }
}

/**
 * 创建评论元素
 * @param {Object} comment - 评论数据
 * @returns {HTMLElement}
 */
function createCommentElement(comment) {
    const div = document.createElement('div');
    div.className = 'comment-item';
    div.dataset.id = comment.id;
    
    const isMember = comment.user?.membership_type === 'member';
    const memberBadge = isMember ? '<span class="member-badge-small">会员</span>' : '';
    
    div.innerHTML = `
        <div class="comment-header">
            <span class="comment-author">${escapeHtml(comment.user?.username || '匿名')}${memberBadge}</span>
            <span class="comment-time">${formatRelativeTime(comment.created_at)}</span>
        </div>
        <div class="comment-content">${escapeHtml(comment.content)}</div>
        <div class="comment-actions">
            <button class="like-btn ${comment.is_liked ? 'liked' : ''}" onclick="toggleCommentLike(${comment.id}, this)">
                <span class="like-icon">👍</span>
                <span class="like-count">${comment.like_count || 0}</span>
            </button>
            <button class="reply-btn" onclick="replyToComment(${comment.id}, '${escapeHtml(comment.user?.username || '匿名')}')">回复</button>
        </div>
        ${comment.replies?.length ? `
            <div class="comment-replies">
                ${comment.replies.map(r => `
                    <div class="reply-item">
                        <span class="reply-author">${escapeHtml(r.user?.username || '匿名')}:</span>
                        <span class="reply-content">${escapeHtml(r.content)}</span>
                    </div>
                `).join('')}
                ${comment.reply_count > 3 ? `<div class="more-replies" onclick="loadReplies(${comment.id})">查看全部 ${comment.reply_count} 条回复</div>` : ''}
            </div>
        ` : ''}
    `;
    
    return div;
}

/**
 * 提交评论
 */
async function submitComment() {
    const input = document.getElementById('commentInput');
    const content = input.value.trim();
    
    if (!content) {
        alert('请输入评论内容');
        return;
    }
    
    if (content.length < 10) {
        alert('评论内容至少需要10个字符');
        return;
    }
    
    const { type, id } = currentCommentTarget;
    if (!type || !id) return;
    
    try {
        const data = await authFetch('/api/comments', {
            method: 'POST',
            body: JSON.stringify({
                target_type: type,
                target_id: id,
                content: content
            })
        });
        
        input.value = '';
        
        // 重新加载评论列表
        commentsPagination.page = 1;
        loadComments(false);
        
    } catch (error) {
        alert(getErrorMessage(error, '评论失败'));
    }
}

/**
 * 回复评论
 * @param {number} parentId - 父评论ID
 * @param {string} username - 被回复用户名称
 */
function replyToComment(parentId, username) {
    const input = document.getElementById('commentInput');
    input.value = `@${username} `;
    input.focus();
    
    // 修改提交函数以支持回复
    const originalSubmit = window.submitComment;
    window.submitComment = async function() {
        const content = input.value.trim();
        if (!content) return;
        
        const { type, id } = currentCommentTarget;
        try {
            await authFetch('/api/comments', {
                method: 'POST',
                body: JSON.stringify({
                    target_type: type,
                    target_id: id,
                    content: content,
                    parent_id: parentId
                })
            });
            
            input.value = '';
            commentsPagination.page = 1;
            loadComments(false);
            
            // 恢复原始提交函数
            window.submitComment = originalSubmit;
        } catch (error) {
            alert(getErrorMessage(error, '回复失败'));
        }
    };
}

/**
 * 切换评论点赞状态
 * @param {number} commentId - 评论ID
 * @param {HTMLElement} btn - 点赞按钮元素
 */
async function toggleCommentLike(commentId, btn) {
    const isLiked = btn.classList.contains('liked');
    const countEl = btn.querySelector('.like-count');
    let currentCount = parseInt(countEl.textContent) || 0;
    
    // 乐观更新UI
    btn.classList.toggle('liked');
    countEl.textContent = isLiked ? currentCount - 1 : currentCount + 1;
    
    try {
        if (isLiked) {
            await authFetch('/api/likes', {
                method: 'DELETE',
                body: JSON.stringify({
                    target_type: 'comment',
                    target_id: String(commentId)
                })
            });
        } else {
            await authFetch('/api/likes', {
                method: 'POST',
                body: JSON.stringify({
                    target_type: 'comment',
                    target_id: String(commentId)
                })
            });
        }
    } catch (error) {
        // 失败时恢复UI
        btn.classList.toggle('liked');
        countEl.textContent = isLiked ? currentCount : currentCount - 1;
        console.error('点赞操作失败:', error);
    }
}

/**
 * 加载评论回复
 * @param {number} commentId - 评论ID
 */
async function loadReplies(commentId) {
    try {
        const data = await authFetch(`/api/comments/${commentId}/replies?page=1&limit=50`);
        
        const commentEl = document.querySelector(`.comment-item[data-id="${commentId}"]`);
        if (!commentEl) return;
        
        const repliesContainer = commentEl.querySelector('.comment-replies');
        if (repliesContainer) {
            repliesContainer.innerHTML = data.items.map(r => `
                <div class="reply-item">
                    <span class="reply-author">${escapeHtml(r.user?.username || '匿名')}:</span>
                    <span class="reply-content">${escapeHtml(r.content)}</span>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('加载回复失败:', error);
    }
}

/**
 * 格式化相对时间
 * @param {string} dateStr - ISO格式时间字符串（UTC）
 * @returns {string}
 */
function formatRelativeTime(dateStr) {
    if (!dateStr) return '-';
    // 确保正确解析UTC时间（添加Z后缀表示UTC）
    const utcDateStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z';
    const date = new Date(utcDateStr);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}天前`;
    return date.toLocaleDateString('zh-CN');
}

// 暴露到全局
window.openCommentsModal = openCommentsModal;
window.closeCommentsModal = closeCommentsModal;
window.openCommentsCommunity = openCommentsCommunity;
window.loadComments = loadComments;
window.submitComment = submitComment;
window.replyToComment = replyToComment;
window.toggleCommentLike = toggleCommentLike;
window.loadReplies = loadReplies;

window.addEventListener('DOMContentLoaded', async () => {
    // 先检查服务器是否重启
    const isRestarted = await checkServerRestart();
    if (isRestarted) {
        autoLogout();
    } else {
        await bootstrapAuth();
        updateAuthUI();
        // 启动服务器状态检测
        startServerCheck();
    }
});

