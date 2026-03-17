// Main JavaScript for CRUXpider Web App

// 全局变量
let searchHistory = [];
let currentAnalysis = null;

// Language switching functionality
let currentLanguage = localStorage.getItem('cruxpider-language') || 'zh';

document.addEventListener('DOMContentLoaded', function() {
    // Initialize event listeners
    initializeEventListeners();
    
    // 加载搜索历史
    loadSearchHistory();
    
    // 检查API状态
    checkAPIStatus();
    
    // Initialize language on page load
    setLanguage(currentLanguage);
});

// 检查API状态
async function checkAPIStatus() {
    try {
        const response = await fetch('/api/health');
        const status = await response.json();
        
        if (status.status === 'healthy') {
            showStatusIndicator('healthy', '所有服务正常运行');
        } else {
            showStatusIndicator('warning', '部分服务不可用');
        }
    } catch (error) {
        showStatusIndicator('error', '无法连接到服务器');
    }
}

// 显示状态指示器
function showStatusIndicator(type, message) {
    const indicator = document.createElement('div');
    indicator.className = `alert alert-${type === 'healthy' ? 'success' : type === 'warning' ? 'warning' : 'danger'} alert-dismissible fade show position-fixed`;
    indicator.style.top = '20px';
    indicator.style.right = '20px';
    indicator.style.zIndex = '9999';
    indicator.innerHTML = `
        <i class="fas fa-${type === 'healthy' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'times-circle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(indicator);
    
    // 自动移除
    setTimeout(() => {
        if (indicator.parentNode) {
            indicator.remove();
        }
    }, 5000);
}

// 保存搜索历史
function saveSearchHistory(title, result) {
    searchHistory.unshift({
        title: title,
        result: result,
        timestamp: new Date().toISOString()
    });
    
    // 只保留最近50个搜索
    if (searchHistory.length > 50) {
        searchHistory = searchHistory.slice(0, 50);
    }
    
    localStorage.setItem('cruxpider_search_history', JSON.stringify(searchHistory));
    updateSearchHistoryUI();
}

// 加载搜索历史
function loadSearchHistory() {
    const saved = localStorage.getItem('cruxpider_search_history');
    if (saved) {
        searchHistory = JSON.parse(saved);
        updateSearchHistoryUI();
    }
}

// 更新搜索历史UI
function updateSearchHistoryUI() {
    const historyContainer = document.getElementById('searchHistory');
    if (!historyContainer) return;
    
    if (searchHistory.length === 0) {
        historyContainer.innerHTML = `
            <div class="card-header">
                <h6 class="mb-0" data-zh="最近搜索" data-en="Recent Searches">最近搜索</h6>
            </div>
            <div class="card-body text-center text-muted">
                <i class="fas fa-history fa-2x mb-2"></i>
                <p data-zh="暂无搜索历史" data-en="No search history">暂无搜索历史</p>
            </div>
        `;
        return;
    }
    
    historyContainer.innerHTML = `
        <div class="card-header d-flex justify-content-between align-items-center">
            <h6 class="mb-0" data-zh="最近搜索" data-en="Recent Searches">最近搜索</h6>
            <button class="btn btn-sm btn-outline-danger" onclick="clearAllHistory()" title="清空全部历史">
                <i class="fas fa-trash-alt"></i>
                <span data-zh="清空" data-en="Clear All">清空</span>
            </button>
        </div>
        <div class="card-body" style="max-height: 35vh; overflow-y: auto;">
            ${searchHistory.map((item, index) => `
                <div class="card mb-2 history-item">
                    <div class="card-body p-2">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1" style="min-width: 0;">
                                <small class="text-muted">${new Date(item.timestamp).toLocaleString()}</small>
                                <div class="fw-bold text-truncate" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                                ${item.result.research_profile?.domains?.[0] ? `<span class="badge bg-secondary">${escapeHtml(item.result.research_profile.domains[0])}</span>` : ''}
                            </div>
                            <div class="btn-group" role="group">
                                <button class="btn btn-sm btn-outline-primary" onclick="loadFromHistory('${escapeHtml(item.title)}')" title="重新搜索">
                                    <i class="fas fa-redo"></i>
                                </button>
                                <button class="btn btn-sm btn-outline-danger" onclick="removeFromHistory(${index})" title="删除此记录">
                                    <i class="fas fa-times"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    // Update language for new elements
    if (window.setLanguage) {
        setLanguage(currentLanguage);
    }
}

// 从历史记录加载
function loadFromHistory(title) {
    document.getElementById('paperTitle').value = title;
    scrollToSection('search-section');
}

// 删除单个历史记录
function removeFromHistory(index) {
    const langTexts = window.langTexts || {};
    const confirmMessage = langTexts.delete_confirm || '确定要删除这条搜索记录吗？';
    
    if (confirm(confirmMessage)) {
        searchHistory.splice(index, 1);
        localStorage.setItem('cruxpider_search_history', JSON.stringify(searchHistory));
        updateSearchHistoryUI();
        
        // 显示删除成功提示
        const successMessage = langTexts.record_deleted || '搜索记录已删除';
        showStatusIndicator('success', successMessage);
    }
}

// 清空全部历史记录
function clearAllHistory() {
    const langTexts = window.langTexts || {};
    const confirmMessage = langTexts.clear_all_confirm || '确定要清空所有搜索历史吗？此操作无法撤销。';
    
    if (confirm(confirmMessage)) {
        searchHistory = [];
        localStorage.removeItem('cruxpider_search_history');
        updateSearchHistoryUI();
        
        // 显示清空成功提示
        const successMessage = langTexts.history_cleared || '已清空所有搜索历史';
        showStatusIndicator('success', successMessage);
    }
}

// HTML转义函数，防止XSS攻击
function escapeHtml(text) {
    const safeText = String(text ?? '');
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return safeText.replace(/[&<>"']/g, function(m) { return map[m]; });
}

function initializeEventListeners() {
    // Single paper search form
    const searchForm = document.getElementById('searchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', handlePaperSearch);
    }

    const topicAssetForm = document.getElementById('topicAssetForm');
    if (topicAssetForm) {
        topicAssetForm.addEventListener('submit', handleTopicAssetSearch);
    }

    const areaExploreForm = document.getElementById('areaExploreForm');
    if (areaExploreForm) {
        areaExploreForm.addEventListener('submit', handleAreaExplore);
    }
    
    // Relevant papers form
    const relevantForm = document.getElementById('relevantForm');
    if (relevantForm) {
        relevantForm.addEventListener('submit', handleRelevantSearch);
    }
    
    // Batch processing form
    const batchForm = document.getElementById('batchForm');
    if (batchForm) {
        batchForm.addEventListener('submit', handleBatchProcessing);
    }
}

// Smooth scroll to section
function scrollToSection(sectionId) {
    const element = document.getElementById(sectionId);
    if (element) {
        element.scrollIntoView({ 
            behavior: 'smooth',
            block: 'start'
        });
    }
}

// Handle single paper search
async function handlePaperSearch(e) {
    e.preventDefault();
    
    const titleInput = document.getElementById('paperTitle');
    const title = titleInput.value.trim();
    
    if (!title) {
        showAlert('请输入论文标题', 'warning');
        return;
    }
    
    const loadingDiv = document.getElementById('searchLoading');
    const resultsDiv = document.getElementById('searchResults');
    
    // Show loading
    loadingDiv.style.display = 'block';
    resultsDiv.style.display = 'none';
    
    try {
        const response = await fetch('/api/search_paper', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ title: title })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displaySearchResults(data);
            // Save to search history
            saveSearchHistory(title, data);
        } else {
            showAlert(data.error || '搜索失败', 'danger');
        }
    } catch (error) {
        showAlert('网络错误，请重试', 'danger');
        console.error('Search error:', error);
    } finally {
        loadingDiv.style.display = 'none';
    }
}

async function handleTopicAssetSearch(e) {
    e.preventDefault();
    await handleResearchAssetSearch({
        mode: 'topic',
        inputId: 'topicQuery',
        loadingId: 'topicAssetsLoading',
        resultsId: 'topicAssetsResults',
        emptyMessage: currentLanguage === 'en' ? 'Please enter a research topic' : '请输入研究主题',
    });
}

async function handleAreaExplore(e) {
    e.preventDefault();
    await handleResearchAssetSearch({
        mode: 'area',
        inputId: 'areaQuery',
        loadingId: 'areaExploreLoading',
        resultsId: 'areaExploreResults',
        emptyMessage: currentLanguage === 'en' ? 'Please enter a research area' : '请输入研究领域',
    });
}

async function handleResearchAssetSearch({ mode, inputId, loadingId, resultsId, emptyMessage }) {
    const input = document.getElementById(inputId);
    const query = (input?.value || '').trim();
    if (!query) {
        showAlert(emptyMessage, 'warning');
        return;
    }

    const loadingDiv = document.getElementById(loadingId);
    const resultsDiv = document.getElementById(resultsId);
    loadingDiv.style.display = 'block';
    resultsDiv.style.display = 'none';

    try {
        const response = await fetch('/api/explore_assets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, mode, max_papers: 5 }),
        });
        const data = await response.json();
        if (response.ok) {
            displayResearchAssetResults(data, resultsId);
        } else {
            showAlert(data.error || '搜索失败', 'danger');
        }
    } catch (error) {
        showAlert(currentLanguage === 'en' ? 'Network error, please retry' : '网络错误，请重试', 'danger');
        console.error('Research asset search error:', error);
    } finally {
        loadingDiv.style.display = 'none';
    }
}

// Display search results
function displaySearchResults(data) {
    const resultsDiv = document.getElementById('searchResults');
    const lang = currentLanguage || 'zh';
    
    // Define language-specific texts
    const texts = {
        zh: {
            journal_conference: '期刊/会议:',
            research_profile: '研究画像:',
            confidence: '置信度:',
            matched_sources: '匹配来源:',
            identifiers: '论文标识:',
            pdf_link: 'PDF链接:',
            repository: '代码仓库:',
            repository_candidates: '候选代码仓库:',
            categories: '分类:',
            datasets: '数据集:',
            methods: '方法:',
            resolution_notes: '解析依据:',
            warnings: '提示:',
            view_pdf: '查看PDF',
            view_code: '查看代码',
            best_match: '最佳匹配',
            score: '分数',
            reasons: '推荐理由',
            source_label: '来源',
            year: '年份',
            no_related: '未找到相关论文，请尝试其他论文标题'
        },
        en: {
            journal_conference: 'Journal/Conference:',
            research_profile: 'Research Profile:',
            confidence: 'Confidence:',
            matched_sources: 'Matched Sources:',
            identifiers: 'Identifiers:',
            pdf_link: 'PDF Link:',
            repository: 'Code Repository:',
            repository_candidates: 'Repository Candidates:',
            categories: 'Categories:',
            datasets: 'Datasets:',
            methods: 'Methods:',
            resolution_notes: 'Resolution Evidence:',
            warnings: 'Warnings:',
            view_pdf: 'View PDF',
            view_code: 'View Code',
            best_match: 'Best Match',
            score: 'Score',
            reasons: 'Why recommended',
            source_label: 'Sources',
            year: 'Year',
            no_related: 'No related papers found. Try another title.'
        }
    };
    
    const t = texts[lang];
    
    let html = `
        <div class="card result-card fade-in">
            <div class="result-header">
                <h4 class="mb-0"><i class="fas fa-file-alt me-2"></i>${escapeHtml(data.title)}</h4>
            </div>
            <div class="result-body">
                <div class="row">
                    <div class="col-md-6">
                        <div class="info-item">
                            <span class="info-label">${t.journal_conference}</span>
                            <span class="info-value">${escapeHtml(data.journal_conference || data.journal || 'N/A')}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">${t.research_profile}</span>
                            <span class="info-value">
                                ${formatResearchProfile(data.research_profile)}
                            </span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">${t.confidence}</span>
                            <span class="info-value">
                                <span class="tag tag-confidence">${formatConfidence(data.confidence)}</span>
                            </span>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="info-item">
                            <span class="info-label">${t.pdf_link}</span>
                            <span class="info-value">
                                ${data.pdf_url && data.pdf_url !== 'N/A' ? 
                                    `<a href="${escapeHtml(data.pdf_url)}" target="_blank"><i class="fas fa-external-link-alt me-1"></i>${t.view_pdf}</a>` : 
                                    'N/A'
                                }
                            </span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">${t.repository}</span>
                            <span class="info-value">
                                ${data.repository_url && data.repository_url !== 'N/A' ? 
                                    `<a href="${escapeHtml(data.repository_url)}" target="_blank"><i class="fab fa-github me-1"></i>${t.view_code}</a>` : 
                                    'N/A'
                                }
                            </span>
                        </div>
                        ${data.matched_sources && data.matched_sources.length > 0 ? `
                        <div class="info-item">
                            <span class="info-label">${t.matched_sources}</span>
                            <span class="info-value">${data.matched_sources.map(source => `<span class="tag tag-source">${escapeHtml(source)}</span>`).join('')}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>

                ${data.identifiers && Object.keys(data.identifiers).length > 0 ? `
                <div class="info-item">
                    <span class="info-label">${t.identifiers}</span>
                    <span class="info-value">${formatIdentifiers(data.identifiers)}</span>
                </div>
                ` : ''}
                
                ${data.categories && data.categories.length > 0 ? `
                <div class="info-item">
                    <span class="info-label">${t.categories}</span>
                    <span class="info-value">
                        ${Array.isArray(data.categories) ? 
                            data.categories.map(cat => `<span class="tag">${escapeHtml(cat)}</span>`).join('') : 
                            `<span class="tag">${escapeHtml(data.categories)}</span>`
                        }
                    </span>
                </div>
                ` : ''}
                
                ${data.datasets && data.datasets.length > 0 ? `
                <div class="info-item">
                    <span class="info-label">${t.datasets}</span>
                    <span class="info-value">
                        ${formatDatasets(data.datasets)}
                    </span>
                </div>
                ` : ''}
                
                ${data.methods && data.methods.length > 0 ? `
                <div class="info-item">
                    <span class="info-label">${t.methods}</span>
                    <span class="info-value">
                        ${Array.isArray(data.methods) ? 
                            data.methods.map(method => `<span class="tag tag-warning">${escapeHtml(method)}</span>`).join('') : 
                            `<span class="tag tag-warning">${escapeHtml(data.methods)}</span>`
                        }
                    </span>
                </div>
                ` : ''}

                ${data.resolution_notes && data.resolution_notes.length > 0 ? `
                <div class="info-item">
                    <span class="info-label">${t.resolution_notes}</span>
                    <span class="info-value">${data.resolution_notes.map(note => `<div class="signal-line">${escapeHtml(note)}</div>`).join('')}</span>
                </div>
                ` : ''}

                ${data.repository_candidates && data.repository_candidates.length > 0 ? `
                <div class="info-item">
                    <span class="info-label">${t.repository_candidates}</span>
                    <span class="info-value">${formatRepositoryCandidates(data.repository_candidates, t)}</span>
                </div>
                ` : ''}

                ${data.warnings && data.warnings.length > 0 ? `
                <div class="info-item">
                    <span class="info-label">${t.warnings}</span>
                    <span class="info-value">${data.warnings.map(warning => `<div class="warning-line">${escapeHtml(warning)}</div>`).join('')}</span>
                </div>
                ` : ''}
            </div>
        </div>
    `;
    
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
}

// Handle relevant papers search
async function handleRelevantSearch(e) {
    e.preventDefault();
    
    const titleInput = document.getElementById('relevantTitle');
    const maxPapersSelect = document.getElementById('maxPapers');
    const title = titleInput.value.trim();
    const maxPapers = maxPapersSelect.value;
    
    if (!title) {
        showAlert('请输入论文标题', 'warning');
        return;
    }
    
    const loadingDiv = document.getElementById('relevantLoading');
    const resultsDiv = document.getElementById('relevantResults');
    
    // Show loading
    loadingDiv.style.display = 'block';
    resultsDiv.style.display = 'none';
    
    try {
        const response = await fetch('/api/find_relevant_papers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                title: title,
                max_papers: maxPapers
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayRelevantResults(data);
        } else {
            showAlert(data.error || '搜索失败', 'danger');
        }
    } catch (error) {
        showAlert('网络错误，请重试', 'danger');
        console.error('Relevant search error:', error);
    } finally {
        loadingDiv.style.display = 'none';
    }
}

// Display relevant papers results
function displayRelevantResults(data) {
    const resultsDiv = document.getElementById('relevantResults');
    const lang = currentLanguage || 'zh';
    const t = {
        title: lang === 'en' ? 'Related Papers' : '相关论文',
        original: lang === 'en' ? 'Original paper' : '原论文',
        found: lang === 'en' ? 'papers found' : '篇相关论文',
        authors: lang === 'en' ? 'Authors' : '作者',
        year: lang === 'en' ? 'Year' : '年份',
        score: lang === 'en' ? 'Score' : '分数',
        signals: lang === 'en' ? 'Signals' : '信号数',
        reasons: lang === 'en' ? 'Why recommended' : '推荐理由',
        sources: lang === 'en' ? 'Sources' : '来源',
        empty: lang === 'en' ? 'No related papers found. Try another title.' : '未找到相关论文，请尝试其他论文标题',
        grouped: lang === 'en' ? 'Research Guide View' : '研究导航分组',
        same_author: lang === 'en' ? 'Same Author' : '同作者线索',
        same_method: lang === 'en' ? 'Same Method' : '同方法线索',
        same_wave: lang === 'en' ? 'Same Wave' : '同研究波段',
        strong_follow_up: lang === 'en' ? 'Strong Follow-up' : '强后续工作'
    };
    
    let html = `
        <div class="card result-card fade-in">
            <div class="result-header">
                <h4 class="mb-0"><i class="fas fa-network-wired me-2"></i>${t.title}</h4>
                <p class="mb-0 mt-2 opacity-75">${t.original}: ${escapeHtml(data.original_title || 'N/A')}</p>
                <small class="opacity-75">${data.total || 0} ${t.found}</small>
            </div>
            <div class="result-body">
                ${data.papers && data.papers.length > 0 ? `
                <div class="paper-list">
                    ${data.papers.map((paper, index) => `
                    <div class="paper-item border-bottom pb-3 mb-3">
                        <div class="d-flex align-items-start">
                            <span class="paper-number me-3">${index + 1}</span>
                            <div class="flex-grow-1">
                                <h6 class="mb-1">
                                    ${paper.url ? 
                                        `<a href="${escapeHtml(paper.url)}" target="_blank" class="text-decoration-none">${escapeHtml(paper.title)}</a>` : 
                                        escapeHtml(paper.title)
                                    }
                                </h6>
                                ${paper.authors && paper.authors.length > 0 ? 
                                    `<p class="mb-1 text-muted small">${t.authors}: ${paper.authors.map(author => escapeHtml(author)).join(', ')}</p>` : 
                                    ''
                                }
                                <div class="paper-meta mt-2">
                                    ${paper.year ? `<span class="paper-meta-chip">${t.year}: ${escapeHtml(paper.year)}</span>` : ''}
                                    ${paper.score ? `<span class="paper-meta-chip">${t.score}: ${escapeHtml(paper.score)}</span>` : ''}
                                    ${paper.signal_count ? `<span class="paper-meta-chip">${t.signals}: ${escapeHtml(paper.signal_count)}</span>` : ''}
                                    ${paper.sources && paper.sources.length > 0 ? `<span class="paper-meta-chip">${t.sources}: ${paper.sources.map(source => escapeHtml(source)).join(', ')}</span>` : ''}
                                </div>
                                ${paper.reasons && paper.reasons.length > 0 ? `<div class="paper-reasons mt-2">${paper.reasons.map(reason => `<div class="signal-line">${escapeHtml(reason)}</div>`).join('')}</div>` : ''}
                            </div>
                        </div>
                    </div>
                    `).join('')}
                </div>
                ` : `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>${t.empty}
                </div>
                `}
                ${data.grouped_papers ? formatRelatedGroups(data.grouped_papers, t) : ''}
            </div>
        </div>
    `;
    
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
}

// Handle batch processing
async function handleBatchProcessing(e) {
    e.preventDefault();
    
    const fileInput = document.getElementById('csvFile');
    const file = fileInput.files[0];
    
    if (!file) {
        showAlert('请选择CSV文件', 'warning');
        return;
    }
    
    if (!file.name.endsWith('.csv')) {
        showAlert('请选择CSV格式文件', 'warning');
        return;
    }
    
    const loadingDiv = document.getElementById('batchLoading');
    const resultsDiv = document.getElementById('batchResults');
    
    // Show loading
    loadingDiv.style.display = 'block';
    resultsDiv.style.display = 'none';
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/batch_process', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            // File download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `processed_${new Date().toISOString().slice(0, 19).replace(/:/g, '')}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            displayBatchResults(true);
        } else {
            const data = await response.json();
            showAlert(data.error || '批量处理失败', 'danger');
        }
    } catch (error) {
        showAlert('网络错误，请重试', 'danger');
        console.error('Batch processing error:', error);
    } finally {
        loadingDiv.style.display = 'none';
    }
}

// Display batch processing results
function displayBatchResults(success) {
    const resultsDiv = document.getElementById('batchResults');
    
    let html = `
        <div class="card result-card fade-in">
            <div class="result-body text-center">
                ${success ? `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle fa-2x mb-3"></i>
                    <h5>批量处理完成！</h5>
                    <p class="mb-0">处理结果已自动下载到您的设备</p>
                </div>
                ` : `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle fa-2x mb-3"></i>
                    <h5>批量处理失败</h5>
                    <p class="mb-0">请检查文件格式并重试</p>
                </div>
                `}
            </div>
        </div>
    `;
    
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
}

function displayResearchAssetResults(data, resultsId) {
    const resultsDiv = document.getElementById(resultsId);
    const lang = currentLanguage || 'zh';
    const labels = {
        zh: {
            assistant_brief: '研究助手摘要',
            about_area: 'What this area is about',
            start_here: '建议从这里开始',
            available_assets: 'What assets are available',
            next_actions: '下一步建议',
            representative_papers: '代表论文',
            common_methods: '常见方法族',
            common_datasets: '常见数据资产',
            code_repositories: '代码仓库',
            reading_path: '推荐阅读路径',
            papers_found: '篇代表论文',
            stage: '阶段',
            route_map: '研究路线图',
        },
        en: {
            assistant_brief: 'Research Assistant Brief',
            about_area: 'What this area is about',
            start_here: 'Start Here',
            available_assets: 'What assets are available',
            next_actions: 'Next Actions',
            representative_papers: 'Representative Papers',
            common_methods: 'Common Method Families',
            common_datasets: 'Common Dataset Assets',
            code_repositories: 'Code Repositories',
            reading_path: 'Suggested Reading Path',
            papers_found: 'representative papers',
            stage: 'Stage',
            route_map: 'Research Route Map',
        }
    };
    const t = labels[lang];

    const html = `
        <div class="card result-card fade-in">
            <div class="result-header">
                <h4 class="mb-0"><i class="fas fa-compass me-2"></i>${escapeHtml(data.query)}</h4>
            </div>
            <div class="result-body">
                ${formatResearchBrief(data.research_brief, data.research_profile, t, lang)}
                ${formatResearchRouteMap(data, t)}
                <div class="mt-4">
                    <div class="asset-panel-title">${t.representative_papers} (${escapeHtml(data.total)} ${t.papers_found})</div>
                    ${formatRepresentativePapers(data.representative_papers)}
                </div>
            </div>
        </div>
    `;

    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
}

// Format datasets for display
function formatDatasets(datasets) {
    if (!datasets || datasets.length === 0) {
        return 'N/A';
    }
    
    if (Array.isArray(datasets)) {
        return datasets.map(dataset => {
            if (typeof dataset === 'object' && dataset.name) {
                return `
                    <div class="dataset-candidate">
                        <div class="dataset-topline">
                            ${dataset.url ? `<a href="${escapeHtml(dataset.url)}" target="_blank" class="dataset-link">${escapeHtml(dataset.name)}</a>` : `<span class="tag tag-success">${escapeHtml(dataset.name)}</span>`}
                            ${dataset.source ? `<span class="paper-meta-chip">${escapeHtml(dataset.source)}</span>` : ''}
                            ${dataset.score ? `<span class="paper-meta-chip">score: ${escapeHtml(dataset.score)}</span>` : ''}
                            <span class="dataset-tier dataset-tier-${escapeHtml(getDatasetTier(dataset))}">${escapeHtml(getDatasetTierLabel(dataset))}</span>
                            ${isPossibleDatasetMention(dataset) ? `<span class="dataset-kind dataset-kind-mention">${escapeHtml(getDatasetMappingLabel())}</span>` : ''}
                        </div>
                        ${dataset.evidence && dataset.evidence.length > 0 ? `<div class="dataset-evidence">${dataset.evidence.map(item => `<div class="signal-line">${escapeHtml(item)}</div>`).join('')}</div>` : ''}
                    </div>
                `;
            } else {
                return `<span class="tag tag-success">${escapeHtml(dataset)}</span>`;
            }
        }).join('');
    } else {
        return `<span class="tag tag-success">${escapeHtml(datasets)}</span>`;
    }
}

function getDatasetTier(dataset) {
    return dataset.confidence_tier || 'weak';
}

function isPossibleDatasetMention(dataset) {
    return (dataset.mapping_status === 'possible_mention') || !dataset.url;
}

function getDatasetTierLabel(dataset) {
    const lang = currentLanguage || 'zh';
    const labels = {
        zh: { strong: '强证据', medium: '中证据', weak: '弱证据' },
        en: { strong: 'Strong', medium: 'Medium', weak: 'Weak' },
    };
    return labels[lang][getDatasetTier(dataset)] || labels[lang].weak;
}

function getDatasetMappingLabel() {
    const lang = currentLanguage || 'zh';
    return lang === 'zh' ? '可能的数据集提及' : 'Possible dataset mention';
}

function formatResearchProfile(profile) {
    if (!profile) {
        return 'N/A';
    }
    const chips = [];
    ['domains', 'tasks', 'method_families', 'artifact_profile', 'community_fit'].forEach(key => {
        (profile[key] || []).slice(0, 3).forEach(item => chips.push(`<span class="tag tag-source">${escapeHtml(item)}</span>`));
    });
    chips.push(`<span class="tag tag-confidence">${escapeHtml(profile.reproducibility_level || 'low')}</span>`);
    if (profile.summary) {
        chips.unshift(`<span class="tag tag-success">${escapeHtml(profile.summary)}</span>`);
    }
    return chips.join('');
}

function formatCountTags(items) {
    if (!items || items.length === 0) {
        return 'N/A';
    }
    return items.map(item => `<span class="tag tag-warning">${escapeHtml(item.name)} · ${escapeHtml(item.count)}</span>`).join('');
}

function formatDatasetCounts(items) {
    if (!items || items.length === 0) {
        return 'N/A';
    }
    return items.map(item => `
        <div class="asset-line">
            ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" class="dataset-link">${escapeHtml(item.name)}</a>` : `<span>${escapeHtml(item.name)}</span>`}
            <span class="paper-meta-chip">${escapeHtml(item.count)}</span>
            ${item.mapping_status === 'possible_mention' ? `<span class="dataset-kind dataset-kind-mention">${escapeHtml(getDatasetMappingLabel())}</span>` : ''}
        </div>
    `).join('');
}

function formatRepositoryCounts(items) {
    if (!items || items.length === 0) {
        return 'N/A';
    }
    return items.map(item => `
        <div class="asset-line">
            <a href="${escapeHtml(item.url)}" target="_blank" class="repo-link">${escapeHtml(item.name)}</a>
            <span class="paper-meta-chip">${escapeHtml(item.count)}</span>
        </div>
    `).join('');
}

function formatReadingPath(items, labels) {
    if (!items || items.length === 0) {
        return 'N/A';
    }
    return items.map(item => `
        <div class="asset-line">
            ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" class="dataset-link">${escapeHtml(item.title)}</a>` : `<span>${escapeHtml(item.title)}</span>`}
            <span class="paper-meta-chip">${escapeHtml(labels.stage)}: ${escapeHtml(item.stage)}</span>
        </div>
    `).join('');
}

function formatRepresentativePapers(items) {
    if (!items || items.length === 0) {
        return '<div class="text-muted">N/A</div>';
    }
    return items.map(item => `
        <div class="related-group-card">
            <div class="related-group-title">${escapeHtml(item.title)}</div>
            <div class="paper-meta">
                ${item.year ? `<span class="paper-meta-chip">${escapeHtml(item.year)}</span>` : ''}
                ${item.journal_conference ? `<span class="paper-meta-chip">${escapeHtml(item.journal_conference)}</span>` : ''}
                ${item.confidence ? `<span class="paper-meta-chip">confidence: ${escapeHtml(item.confidence)}</span>` : ''}
            </div>
            <div class="mt-2">${formatResearchProfile(item.research_profile)}</div>
        </div>
    `).join('');
}

function formatResearchBrief(brief, profile, labels, lang) {
    const headline = brief?.headline || profile?.summary || 'N/A';
    const starter = brief?.starter_paper || {};
    const actions = brief?.actions || [];
    return `
        <div class="assistant-brief">
            <div class="assistant-headline">${escapeHtml(headline)}</div>
            <div class="info-item">
                <span class="info-label">${lang === 'en' ? 'Research Profile:' : '研究画像:'}</span>
                <span class="info-value">${formatResearchProfile(profile)}</span>
            </div>
            <div class="asset-grid asset-grid-brief">
                <div class="asset-panel asset-panel-brief">
                    <div class="asset-panel-title">${labels.start_here}</div>
                    <div class="assistant-line">
                        ${starter.url ? `<a href="${escapeHtml(starter.url)}" target="_blank" class="dataset-link">${escapeHtml(starter.title || 'N/A')}</a>` : `<span>${escapeHtml(starter.title || 'N/A')}</span>`}
                    </div>
                </div>
                <div class="asset-panel asset-panel-brief">
                    <div class="asset-panel-title">${labels.next_actions}</div>
                    ${actions.length > 0 ? actions.map(item => `<div class="assistant-line">${escapeHtml(item)}</div>`).join('') : '<div class="assistant-line">N/A</div>'}
                </div>
            </div>
        </div>
    `;
}

function formatResearchRouteMap(data, labels) {
    return `
        <div class="route-map">
            <div class="route-map-title">${labels.route_map}</div>
            <div class="route-map-grid">
                <div class="route-step">
                    <div class="route-step-index">1</div>
                    <div class="route-step-title">${labels.about_area}</div>
                    <div class="route-step-body">${formatResearchProfile(data.research_profile)}</div>
                </div>
                <div class="route-step">
                    <div class="route-step-index">2</div>
                    <div class="route-step-title">${labels.start_here}</div>
                    <div class="route-step-body">${formatReadingPath(data.reading_path?.slice(0, 2), labels)}</div>
                </div>
                <div class="route-step">
                    <div class="route-step-index">3</div>
                    <div class="route-step-title">${labels.available_assets}</div>
                    <div class="route-step-body">
                        <div class="route-assets-block">
                            <div class="asset-panel-title">${labels.common_methods}</div>
                            <div>${formatCountTags(data.common_methods)}</div>
                        </div>
                        <div class="route-assets-block">
                            <div class="asset-panel-title">${labels.common_datasets}</div>
                            <div>${formatDatasetCounts(data.common_datasets)}</div>
                        </div>
                        <div class="route-assets-block">
                            <div class="asset-panel-title">${labels.code_repositories}</div>
                            <div>${formatRepositoryCounts(data.code_repositories)}</div>
                        </div>
                    </div>
                </div>
                <div class="route-step">
                    <div class="route-step-index">4</div>
                    <div class="route-step-title">${labels.next_actions}</div>
                    <div class="route-step-body">
                        ${(data.research_brief?.actions || []).length > 0
                            ? data.research_brief.actions.map(item => `<div class="assistant-line">${escapeHtml(item)}</div>`).join('')
                            : '<div class="assistant-line">N/A</div>'}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function formatConfidence(confidence) {
    if (confidence === null || confidence === undefined) {
        return 'N/A';
    }
    const numeric = Number(confidence);
    if (Number.isNaN(numeric)) {
        return escapeHtml(confidence);
    }
    return `${Math.round(numeric * 100)}%`;
}

function formatIdentifiers(identifiers) {
    return Object.entries(identifiers).map(([key, value]) => {
        return `<span class="tag tag-source">${escapeHtml(key)}: ${escapeHtml(value)}</span>`;
    }).join('');
}

function formatRepositoryCandidates(candidates, texts) {
    return candidates.slice(0, 5).map((candidate, index) => `
        <div class="repo-candidate">
            <div class="repo-topline">
                <span class="repo-rank">${texts.best_match} ${index + 1}</span>
                <span class="repo-score">${texts.score}: ${escapeHtml(candidate.score)}</span>
            </div>
            <a href="${escapeHtml(candidate.url)}" target="_blank" class="repo-link">
                <i class="fab fa-github me-1"></i>${escapeHtml(candidate.name)}
            </a>
            ${candidate.description ? `<div class="repo-description">${escapeHtml(candidate.description)}</div>` : ''}
            ${candidate.reasons && candidate.reasons.length > 0 ? `<div class="repo-reasons">${candidate.reasons.map(reason => `<div class="signal-line">${escapeHtml(reason)}</div>`).join('')}</div>` : ''}
        </div>
    `).join('');
}

function formatRelatedGroups(groupedPapers, texts) {
    const sections = [
        ['same_author', texts.same_author],
        ['same_method', texts.same_method],
        ['same_wave', texts.same_wave],
        ['strong_follow_up', texts.strong_follow_up],
    ];

    const visibleSections = sections.filter(([key]) => groupedPapers[key] && groupedPapers[key].length > 0);
    if (visibleSections.length === 0) {
        return '';
    }

    return `
        <div class="related-groups mt-4">
            <h5 class="mb-3">${texts.grouped}</h5>
            ${visibleSections.map(([key, label]) => `
                <div class="related-group-card">
                    <div class="related-group-title">${label}</div>
                    <div class="related-group-list">
                        ${groupedPapers[key].slice(0, 4).map(paper => `
                            <div class="related-group-item">
                                ${paper.url ? `<a href="${escapeHtml(paper.url)}" target="_blank">${escapeHtml(paper.title)}</a>` : escapeHtml(paper.title)}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

// Show alert message
function showAlert(message, type = 'info') {
    // Remove existing alerts
    const existingAlerts = document.querySelectorAll('.temp-alert');
    existingAlerts.forEach(alert => alert.remove());
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show temp-alert`;
    alertDiv.innerHTML = `
        <i class="fas fa-${getAlertIcon(type)} me-2"></i>
        ${escapeHtml(message)}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Insert at the top of the page content
    const container = document.querySelector('.container');
    if (container) {
        container.insertAdjacentElement('afterbegin', alertDiv);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Get alert icon based on type
function getAlertIcon(type) {
    const icons = {
        'success': 'check-circle',
        'warning': 'exclamation-triangle',
        'danger': 'exclamation-circle',
        'info': 'info-circle'
    };
    return icons[type] || 'info-circle';
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    if (text === null || text === undefined) {
        return 'N/A';
    }
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Toggle language between Chinese and English
function toggleLanguage() {
    currentLanguage = currentLanguage === 'zh' ? 'en' : 'zh';
    setLanguage(currentLanguage);
    localStorage.setItem('cruxpider-language', currentLanguage);
}

// Set language for the interface
function setLanguage(lang) {
    currentLanguage = lang;
    
    // Update flag and text
    const langFlag = document.getElementById('langFlag');
    const langText = document.getElementById('langText');
    
    if (langFlag && langText) {
        if (lang === 'zh') {
            langFlag.textContent = '🇺🇸';
            langText.textContent = 'English';
        } else {
            langFlag.textContent = '🇨🇳';
            langText.textContent = '中文';
        }
    }
    
    // Update all elements with data-en and data-zh attributes
    const elements = document.querySelectorAll('[data-en][data-zh]');
    elements.forEach(element => {
        const text = lang === 'en' ? element.getAttribute('data-en') : element.getAttribute('data-zh');
        if (text) {
            element.textContent = text;
        }
    });
    
    // Update placeholder texts
    const placeholderElements = document.querySelectorAll('[data-placeholder-en][data-placeholder-zh]');
    placeholderElements.forEach(element => {
        const placeholder = lang === 'en' ? element.getAttribute('data-placeholder-en') : element.getAttribute('data-placeholder-zh');
        if (placeholder) {
            element.placeholder = placeholder;
        }
    });
    
    // Update option texts in select elements
    const optionElements = document.querySelectorAll('option[data-en][data-zh]');
    optionElements.forEach(option => {
        const text = lang === 'en' ? option.getAttribute('data-en') : option.getAttribute('data-zh');
        if (text) {
            option.textContent = text;
        }
    });
    
    // Update loading and status messages
    updateDynamicTexts(lang);
}

function updateDynamicTexts(lang) {
    // Update search result labels
    const resultLabels = {
        'journal_conference': lang === 'en' ? 'Journal/Conference:' : '期刊/会议:',
        'research_profile': lang === 'en' ? 'Research Profile:' : '研究画像:',
        'pdf_url': lang === 'en' ? 'PDF Link:' : 'PDF链接:',
        'repository_url': lang === 'en' ? 'Code Repository:' : '代码仓库:',
        'categories': lang === 'en' ? 'Categories:' : '分类:',
        'datasets': lang === 'en' ? 'Datasets:' : '数据集:',
        'methods': lang === 'en' ? 'Methods:' : '方法:',
        'view_pdf': lang === 'en' ? 'View PDF' : '查看PDF',
        'view_code': lang === 'en' ? 'View Code' : '查看代码',
        'no_search_history': lang === 'en' ? 'No search history' : '暂无搜索历史',
        'searching': lang === 'en' ? 'Searching...' : '搜索中...',
        'analyzing': lang === 'en' ? 'Analyzing paper information, please wait...' : '正在分析论文信息，请稍候...',
        'finding_related': lang === 'en' ? 'Finding related papers, please wait...' : '正在查找相关论文，请稍候...',
        'processing': lang === 'en' ? 'Processing file, please wait...' : '正在批量处理文件，请稍候...',
        'delete_confirm': lang === 'en' ? 'Are you sure you want to delete this search record?' : '确定要删除这条搜索记录吗？',
        'clear_all_confirm': lang === 'en' ? 'Are you sure you want to clear all search history? This action cannot be undone.' : '确定要清空所有搜索历史吗？此操作无法撤销。',
        'record_deleted': lang === 'en' ? 'Search record deleted successfully' : '搜索记录已删除',
        'history_cleared': lang === 'en' ? 'All search history cleared successfully' : '已清空所有搜索历史'
    };
    
    // Store for use in other functions
    window.langTexts = resultLabels;
}

// Override displaySearchResults to use current language
function updateSearchResultsLanguage(data) {
    if (!window.langTexts) return;
    
    // This will be called when displaying results to use current language
    const langTexts = window.langTexts;
    
    // Update any dynamic content based on current language
    const loadingElements = document.querySelectorAll('.visually-hidden');
    loadingElements.forEach(el => {
        if (el.textContent.includes('搜索中') || el.textContent.includes('Searching')) {
            el.textContent = langTexts.searching;
        }
    });
}
