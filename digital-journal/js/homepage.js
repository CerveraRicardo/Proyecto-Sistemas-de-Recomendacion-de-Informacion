/**
 * HOMEPAGE.JS - JavaScript para Homepage ACTUALIZADO
 * Conecta directamente con la API de recomendaciones persistentes
 * ACTUALIZADO: Navegación a páginas de artículos individuales
 */

// ================================
// CONFIGURACIÓN GLOBAL
// ================================

const CONFIG = {
    API_BASE_URL: 'http://localhost:8000',
    REFRESH_INTERVAL: 300000, // 5 minutos
    RETRY_ATTEMPTS: 3,
    RETRY_DELAY: 2000,
    ARTICLES_PER_SECTION: 4
};

// ================================
// ESTADO GLOBAL
// ================================

const AppState = {
    isOnline: false,
    lastUpdate: null,
    recommendations: {
        recent: [],
        featured: [],
        popular: [],
        trending: []
    },
    systemStats: {},
    loading: new Set(),
    errors: new Map()
};

// ================================
// SERVICIO DE API
// ================================

class ApiService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                ...options.headers
            },
            timeout: 10000,
            ...options
        };

        try {
            console.log(`🔄 API Request: ${endpoint}`);
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            console.log(`✅ API Response: ${endpoint}`, data);
            return data;
            
        } catch (error) {
            console.error(`❌ API Error: ${endpoint}`, error);
            throw error;
        }
    }

    // Endpoint principal para verificar estado del sistema
    async getSystemStatus() {
        return await this.request('/');
    }

    // Endpoints específicos para cada tipo de recomendación
    async getRecentArticles(limit = CONFIG.ARTICLES_PER_SECTION) {
        return await this.request(`/admin/homepage/recent?limit=${limit}`);
    }

    async getFeaturedArticles(limit = CONFIG.ARTICLES_PER_SECTION) {
        return await this.request(`/admin/homepage/featured?limit=${limit}`);
    }

    async getPopularArticles(limit = CONFIG.ARTICLES_PER_SECTION) {
        return await this.request(`/admin/homepage/popular?limit=${limit}`);
    }

    async getTrendingArticles(limit = CONFIG.ARTICLES_PER_SECTION) {
        return await this.request(`/admin/homepage/trending?limit=${limit}`);
    }

    // Endpoint para estadísticas del sistema  
    async getSystemInsights() {
        return await this.request('/status');
    }

    // Endpoint para estado del cache
    async getCacheStatus() {
        return await this.request('/admin/cache-status');
    }

    // Endpoint de salud del sistema
    async getHealthCheck() {
        return await this.request('/health');
    }
}

// ================================
// INSTANCIA GLOBAL DE API
// ================================

const api = new ApiService(CONFIG.API_BASE_URL);

// ================================
// UTILIDADES
// ================================

const Utils = {
    formatDate(dateString) {
        if (!dateString) return 'Fecha no disponible';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('es-ES', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
        } catch (error) {
            return 'Fecha no válida';
        }
    },

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    cleanAuthors(authors) {
        if (!authors) return 'Autor desconocido';
        
        // Separar por ";" y limpiar duplicados
        const authorList = authors.split(';')
            .map(author => author.trim())
            .filter(author => author && author.length > 2 && !author.match(/^\s*;?\s*$/))
            // Remover nombres duplicados
            .filter((author, index, arr) => {
                const cleanAuthor = author.replace(/\s+/g, ' ').toLowerCase();
                return arr.findIndex(a => a.replace(/\s+/g, ' ').toLowerCase() === cleanAuthor) === index;
            })
            // Tomar solo los primeros 3 autores para evitar listas muy largas
            .slice(0, 3);
        
        if (authorList.length === 0) return 'Autor desconocido';
        
        return authorList.join(', ') + (authorList.length >= 3 ? ' et al.' : '');
    },

    cleanHtmlContent(content) {
        if (!content) return '';
        
        // Crear un elemento temporal para decodificar HTML
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = content;
        
        // Obtener solo el texto sin tags HTML
        const textContent = tempDiv.textContent || tempDiv.innerText || '';
        
        // Limpiar espacios extra y caracteres especiales
        return textContent
            .replace(/\s+/g, ' ')
            .trim();
    },

    truncateText(text, maxLength = 150) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength).trim() + '...';
    },

    formatNumber(num) {
        if (!num) return '0';
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toString();
    },

    getTimeAgo(date) {
        const now = new Date();
        const diffInMinutes = Math.floor((now - date) / (1000 * 60));
        
        if (diffInMinutes < 1) return 'hace un momento';
        if (diffInMinutes < 60) return `hace ${diffInMinutes} minutos`;
        
        const diffInHours = Math.floor(diffInMinutes / 60);
        if (diffInHours < 24) return `hace ${diffInHours} horas`;
        
        const diffInDays = Math.floor(diffInHours / 24);
        return `hace ${diffInDays} días`;
    },

    getAlgorithmName(algorithm) {
        const algorithmNames = {
            'tfidf_cosine': 'Análisis de Contenido',
            'content_based_tfidf': 'Similitud de Texto',
            'hybrid_content_collaborative': 'IA Híbrida',
            'batch_tfidf_cosine': 'Análisis Avanzado',
            'recent': 'Ordenamiento Temporal',
            'featured': 'Algoritmo de Relevancia',
            'popular': 'Índice de Popularidad',
            'trending': 'Detección de Tendencias'
        };
        return algorithmNames[algorithm] || 'Recomendación IA';
    }
};

// ================================
// MANAGER DE UI
// ================================

const UIManager = {
    setLoading(elementId, isLoading) {
        const element = document.getElementById(elementId);
        if (element) {
            if (isLoading) {
                element.classList.add('active');
                AppState.loading.add(elementId);
            } else {
                element.classList.remove('active');
                AppState.loading.delete(elementId);
            }
        }
    },

    showError(containerId, message, details = null) {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = `
                <div class="error-state">
                    <div class="error-icon">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="error-content">
                        <h3>Error de Conexión</h3>
                        <p>${Utils.escapeHtml(message)}</p>
                        ${details ? `<small class="error-details">${Utils.escapeHtml(details)}</small>` : ''}
                        <button class="retry-btn" onclick="retryOperation('${containerId}')">
                            <i class="fas fa-redo"></i> Reintentar
                        </button>
                    </div>
                </div>
            `;
        }
        AppState.errors.set(containerId, message);
    },

    showNoResults(containerId, message = 'No hay artículos disponibles') {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = `
                <div class="no-results">
                    <div class="no-results-icon">
                        <i class="fas fa-search"></i>
                    </div>
                    <div class="no-results-content">
                        <h3>Sin Resultados</h3>
                        <p>${Utils.escapeHtml(message)}</p>
                    </div>
                </div>
            `;
        }
    },

    updateApiStatus(isOnline, statusText = '') {
        const statusDot = document.getElementById('status-dot');
        const statusTextEl = document.getElementById('status-text');
        const healthIndicator = document.getElementById('health-indicator');
        const healthText = document.getElementById('health-text');

        AppState.isOnline = isOnline;

        if (statusDot) {
            statusDot.className = `status-dot ${isOnline ? 'online' : 'offline'}`;
        }

        if (statusTextEl) {
            statusTextEl.textContent = statusText || (isOnline ? 'API Conectada' : 'API Desconectada');
        }

        if (healthIndicator) {
            healthIndicator.className = `health-indicator ${isOnline ? 'healthy' : 'unhealthy'}`;
        }

        if (healthText) {
            healthText.textContent = statusText || (isOnline ? 'Sistema operativo' : 'Verificando conexión...');
        }
    },

    updateLastUpdate() {
        const updateTimeEl = document.getElementById('update-time');
        if (updateTimeEl) {
            AppState.lastUpdate = new Date();
            updateTimeEl.textContent = Utils.getTimeAgo(AppState.lastUpdate);
        }
    },

    animateElements(selector, delay = 100) {
        const elements = document.querySelectorAll(selector);
        elements.forEach((el, index) => {
            setTimeout(() => {
                el.classList.add('fade-in');
            }, index * delay);
        });
    }
};

// ================================
// MANAGER DE RECOMENDACIONES
// ================================

const RecommendationsManager = {
    // Mapeo de tipos a funciones de API
    apiMethods: {
        recent: (api, limit) => api.getRecentArticles(limit),
        featured: (api, limit) => api.getFeaturedArticles(limit),
        popular: (api, limit) => api.getPopularArticles(limit),
        trending: (api, limit) => api.getTrendingArticles(limit)
    },

    async loadAllRecommendations() {
        console.log('🔄 Cargando todas las recomendaciones desde API...');
        
        const types = ['recent', 'featured', 'popular', 'trending'];
        const promises = types.map(type => this.loadRecommendationType(type));
        
        try {
            const results = await Promise.allSettled(promises);
            
            // Verificar resultados
            results.forEach((result, index) => {
                if (result.status === 'rejected') {
                    console.error(`❌ Error cargando ${types[index]}:`, result.reason);
                }
            });
            
            UIManager.updateLastUpdate();
            console.log('✅ Carga de recomendaciones completada');
            
        } catch (error) {
            console.error('❌ Error cargando recomendaciones:', error);
        }
    },

    async loadRecommendationType(type) {
        const loadingId = `${type}-loading`;
        const containerId = `${type}-articles`;
        
        console.log(`🔄 Cargando recomendaciones tipo: ${type}`);
        UIManager.setLoading(loadingId, true);
        AppState.errors.delete(containerId);
        
        try {
            // Usar el método de API correspondiente
            const apiMethod = this.apiMethods[type];
            if (!apiMethod) {
                throw new Error(`Tipo de recomendación no válido: ${type}`);
            }
            
            console.log(`📡 Llamando API para ${type}...`);
            const data = await apiMethod(api, CONFIG.ARTICLES_PER_SECTION);
            console.log(`📊 Respuesta API para ${type}:`, data);
            
            const articles = data.articles || [];
            
            if (articles.length === 0) {
                console.warn(`⚠️ No se encontraron artículos para ${type}`);
                UIManager.showNoResults(containerId, `No hay artículos ${type} disponibles en este momento`);
            } else {
                AppState.recommendations[type] = articles;
                this.renderArticles(containerId, articles, type);
                console.log(`✅ ${type}: ${articles.length} artículos renderizados`);
            }
            
        } catch (error) {
            console.error(`❌ Error cargando ${type}:`, error);
            
            // Mostrar detalles específicos del error
            let errorMessage = `Error cargando artículos ${type}`;
            let errorDetails = error.message;
            
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                errorDetails = 'No se puede conectar con la API. Verifique que esté ejecutándose en http://localhost:8000';
            } else if (error.message.includes('HTTP 404')) {
                errorDetails = `Endpoint /admin/homepage/${type} no encontrado`;
            } else if (error.message.includes('HTTP 500')) {
                errorDetails = 'Error interno del servidor API';
            }
            
            UIManager.showError(containerId, errorMessage, errorDetails);
        } finally {
            UIManager.setLoading(loadingId, false);
        }
    },

    renderArticles(containerId, articles, type) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (!articles || articles.length === 0) {
            UIManager.showNoResults(containerId, `No hay artículos ${type} disponibles`);
            return;
        }

        container.innerHTML = articles.map(article => this.createArticleCard(article, type)).join('');
        
        // Animar elementos
        setTimeout(() => {
            UIManager.animateElements(`#${containerId} .article-card`, 100);
        }, 50);
    },

    createArticleCard(article, type) {
        const score = article.score || 0;
        const rank = article.rank || 0;
        const algorithm = Utils.getAlgorithmName(type);
        
        // Limpiar datos de la API
        const cleanTitle = Utils.escapeHtml(article.title || 'Sin título');
        const cleanAuthors = Utils.cleanAuthors(article.authors);
        const cleanAbstract = Utils.cleanHtmlContent(article.abstract);
        const truncatedAbstract = Utils.truncateText(cleanAbstract || 'Sin resumen disponible', 120);
        
        return `
            <div class="article-card" onclick="openArticleDetail(${article.submission_id || article.publication_id})">
                <div class="article-header">
                    <div class="article-rank">
                        <span class="rank-number">#${rank}</span>
                    </div>
                    <h3 class="article-title">${cleanTitle}</h3>
                    <p class="article-authors">${Utils.escapeHtml(cleanAuthors)}</p>
                </div>
                <div class="article-body">
                    <p class="article-abstract">${Utils.escapeHtml(truncatedAbstract)}</p>
                </div>
                <div class="article-footer">
                    <div class="article-meta">
                        <span class="article-algorithm">
                            <i class="fas fa-brain"></i>
                            ${algorithm}
                        </span>
                        ${score > 0 ? `
                            <span class="article-score">
                                <i class="fas fa-star"></i>
                                ${(score * 100).toFixed(0)}%
                            </span>
                        ` : ''}
                    </div>
                    <div class="article-actions">
                        <button class="action-btn" onclick="event.stopPropagation(); copyArticleLink(${article.submission_id || article.publication_id})" title="Copiar enlace">
                            <i class="fas fa-link"></i>
                        </button>
                        <button class="action-btn" onclick="event.stopPropagation(); showArticleInfo(${article.publication_id || article.submission_id}, '${type}')" title="Más información">
                            <i class="fas fa-info"></i>
                        </button>
                        <button class="action-btn primary" onclick="event.stopPropagation(); openArticleDetail(${article.submission_id || article.publication_id})" title="Ver artículo completo">
                            <i class="fas fa-eye"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
};

// ================================
// MANAGER DE ESTADÍSTICAS
// ================================

const StatsManager = {
    async loadSystemStats() {
        try {
            const [statusData, cacheData] = await Promise.all([
                api.getSystemInsights(),
                api.getCacheStatus()
            ]);

            this.updateHeroStats(statusData, cacheData);
            this.updateFooterStats(statusData, cacheData);

        } catch (error) {
            console.error('❌ Error cargando estadísticas:', error);
            this.showStatsError();
        }
    },

    updateHeroStats(statusData, cacheData) {
        const totalArticlesEl = document.getElementById('total-articles');
        const totalRecommendationsEl = document.getElementById('total-recommendations');
        const systemAccuracyEl = document.getElementById('system-accuracy');

        if (totalArticlesEl) {
            // Usar datos del endpoint /status
            const articlesCount = statusData.today_statistics?.articles_with_recommendations || 
                                statusData.current_data?.articles_with_recommendations ||
                                cacheData.cache_statistics?.unique_targets || 0;
            totalArticlesEl.textContent = Utils.formatNumber(articlesCount);
        }

        if (totalRecommendationsEl) {
            // Usar datos del endpoint /status  
            const recsCount = statusData.today_statistics?.total_recommendations || 
                            statusData.current_data?.total_recommendations_today ||
                            cacheData.cache_statistics?.total_records || 0;
            totalRecommendationsEl.textContent = Utils.formatNumber(recsCount);
        }

        if (systemAccuracyEl) {
            // Usar promedio de similitud como indicador de precisión
            const accuracy = statusData.today_statistics?.average_similarity ||
                           cacheData.cache_statistics?.similarity_range?.average || 0;
            systemAccuracyEl.textContent = `${(accuracy * 100).toFixed(0)}%`;
        }
    },

    updateFooterStats(statusData, cacheData) {
        const footerArticlesEl = document.getElementById('footer-articles');
        const footerRecommendationsEl = document.getElementById('footer-recommendations');

        if (footerArticlesEl) {
            const articlesCount = statusData.today_statistics?.articles_with_recommendations || 
                                statusData.current_data?.articles_with_recommendations ||
                                cacheData.cache_statistics?.unique_targets || 0;
            footerArticlesEl.textContent = Utils.formatNumber(articlesCount);
        }

        if (footerRecommendationsEl) {
            const recsCount = statusData.today_statistics?.total_recommendations || 
                            statusData.current_data?.total_recommendations_today ||
                            cacheData.cache_statistics?.total_records || 0;
            footerRecommendationsEl.textContent = Utils.formatNumber(recsCount);
        }
    },

    showStatsError() {
        const placeholderElements = [
            'total-articles', 'total-recommendations', 'system-accuracy',
            'footer-articles', 'footer-recommendations'
        ];

        placeholderElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = '--';
                element.style.color = 'var(--error-color, #ef4444)';
            }
        });
    }
};

// ================================
// FUNCIONES GLOBALES ACTUALIZADAS
// ================================

// NUEVA: Función para abrir página de detalles de artículo
window.openArticleDetail = function(articleId) {
    if (articleId) {
        console.log(`🔗 Navegando a detalles del artículo: ${articleId}`);
        window.location.href = `article-detail.html?id=${articleId}`;
    }
};

// Función legacy para compatibilidad
window.openArticle = function(articleId) {
    if (articleId) {
        // Abrir en nueva pestaña (comportamiento legacy)
        const url = `article/view/${articleId}`;
        window.open(url, '_blank');
    }
};

// Función para copiar enlace de artículo
window.copyArticleLink = async function(articleId) {
    const url = `${window.location.origin}/article-detail.html?id=${articleId}`;
    try {
        await navigator.clipboard.writeText(url);
        showNotification('Enlace copiado al portapapeles', 'success');
    } catch (error) {
        console.error('Error copiando enlace:', error);
        // Fallback para navegadores que no soportan clipboard API
        const textArea = document.createElement('textarea');
        textArea.value = url;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showNotification('Enlace copiado al portapapeles', 'success');
        } catch (err) {
            showNotification('Error copiando enlace', 'error');
        }
        document.body.removeChild(textArea);
    }
};

// Función para mostrar información del artículo
window.showArticleInfo = function(articleId, type) {
    // Buscar el artículo en las recomendaciones cargadas
    let article = null;
    if (type && AppState.recommendations[type]) {
        article = AppState.recommendations[type].find(a => 
            (a.publication_id === articleId) || (a.submission_id === articleId)
        );
    }
    
    if (!article) {
        // Buscar en todas las recomendaciones
        for (const recType in AppState.recommendations) {
            article = AppState.recommendations[recType].find(a => 
                (a.publication_id === articleId) || (a.submission_id === articleId)
            );
            if (article) break;
        }
    }
    
    if (article) {
        // Limpiar datos para mostrar
        const cleanTitle = article.title || 'Sin título';
        const cleanAuthors = Utils.cleanAuthors(article.authors);
        const cleanAbstract = Utils.cleanHtmlContent(article.abstract);
        
        const modal = createModal('Información del Artículo', `
            <div class="article-info-modal">
                <h3>${Utils.escapeHtml(cleanTitle)}</h3>
                <p><strong>Autores:</strong> ${Utils.escapeHtml(cleanAuthors)}</p>
                ${article.rank ? `<p><strong>Ranking:</strong> #${article.rank}</p>` : ''}
                ${article.score ? `<p><strong>Puntuación IA:</strong> ${(article.score * 100).toFixed(1)}%</p>` : ''}
                ${cleanAbstract ? `<p><strong>Resumen:</strong> ${Utils.escapeHtml(cleanAbstract)}</p>` : ''}
                <div class="modal-actions">
                    <button onclick="openArticleDetail(${articleId})" class="btn-primary">
                        <i class="fas fa-eye"></i> Ver Artículo Completo
                    </button>
                    <button onclick="copyArticleLink(${articleId})" class="btn-secondary">
                        <i class="fas fa-link"></i> Copiar Enlace
                    </button>
                </div>
            </div>
        `);
        showModal(modal);
    } else {
        showNotification('Información del artículo no disponible', 'warning');
    }
};

// Función para refrescar recomendaciones específicas
window.refreshRecommendations = async function(type) {
    console.log(`🔄 Refrescando recomendaciones: ${type}`);
    try {
        await RecommendationsManager.loadRecommendationType(type);
        showNotification(`Recomendaciones ${type} actualizadas`, 'success');
    } catch (error) {
        showNotification(`Error actualizando ${type}`, 'error');
    }
};

// Función para reintentar operación
window.retryOperation = function(containerId) {
    const type = containerId.replace('-articles', '');
    if (['recent', 'featured', 'popular', 'trending'].includes(type)) {
        refreshRecommendations(type);
    }
};

// ================================
// SISTEMA DE NOTIFICACIONES
// ================================

let notificationCount = 0;

function showNotification(message, type = 'info', duration = 3000) {
    const container = getOrCreateNotificationContainer();
    const notificationId = `notification-${++notificationCount}`;
    
    const notification = document.createElement('div');
    notification.id = notificationId;
    notification.className = `notification notification-${type}`;
    
    const icons = {
        success: 'fas fa-check-circle',
        error: 'fas fa-exclamation-circle',
        warning: 'fas fa-exclamation-triangle',
        info: 'fas fa-info-circle'
    };
    
    notification.innerHTML = `
        <div class="notification-content">
            <i class="${icons[type] || icons.info}"></i>
            <span>${Utils.escapeHtml(message)}</span>
            <button onclick="removeNotification('${notificationId}')" class="notification-close">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    
    container.appendChild(notification);
    
    // Auto-remove
    setTimeout(() => removeNotification(notificationId), duration);
    
    // Animate in
    setTimeout(() => notification.classList.add('show'), 10);
}

function removeNotification(notificationId) {
    const notification = document.getElementById(notificationId);
    if (notification) {
        notification.classList.add('removing');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }
}

function getOrCreateNotificationContainer() {
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.className = 'notification-container';
        document.body.appendChild(container);
    }
    return container;
}

// ================================
// SISTEMA DE MODALES
// ================================

function createModal(title, content) {
    const modalId = `modal-${Date.now()}`;
    return {
        id: modalId,
        html: `
            <div class="modal-overlay" id="${modalId}">
                <div class="modal-dialog">
                    <div class="modal-header">
                        <h3>${Utils.escapeHtml(title)}</h3>
                        <button onclick="hideModal('${modalId}')" class="modal-close">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-body">
                        ${content}
                    </div>
                </div>
            </div>
        `
    };
}

function showModal(modal) {
    document.body.insertAdjacentHTML('beforeend', modal.html);
    const modalElement = document.getElementById(modal.id);
    setTimeout(() => modalElement.classList.add('show'), 10);
    document.body.style.overflow = 'hidden';
}

function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hiding');
        setTimeout(() => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
            document.body.style.overflow = 'auto';
        }, 300);
    }
}

// ================================
// NAVEGACIÓN MÓVIL
// ================================

function setupMobileNavigation() {
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');
    
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', () => {
            navMenu.classList.toggle('active');
        });
        
        // Cerrar menú al hacer click fuera
        document.addEventListener('click', (e) => {
            if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
                navMenu.classList.remove('active');
            }
        });
        
        // Cerrar menú al hacer click en un enlace
        navMenu.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', () => {
                navMenu.classList.remove('active');
            });
        });
    }
}

// ================================
// VERIFICACIÓN DE CONECTIVIDAD
// ================================

async function checkConnectivity() {
    try {
        // Primero intentar el health check
        const response = await api.getHealthCheck();
        if (response.status === 'healthy') {
            UIManager.updateApiStatus(true, 'Sistema saludable');
            return true;
        } else {
            UIManager.updateApiStatus(false, 'Sistema no saludable');
            return false;
        }
    } catch (error) {
        // Si falla el health check, intentar endpoint principal
        try {
            const fallbackResponse = await api.getSystemStatus();
            if (fallbackResponse.message) {
                UIManager.updateApiStatus(true, 'API conectada');
                return true;
            }
        } catch (fallbackError) {
            console.error('Error de conectividad:', fallbackError);
        }
        
        UIManager.updateApiStatus(false, 'Error de conexión');
        return false;
    }
}

// ================================
// AUTO-REFRESH
// ================================

function setupAutoRefresh() {
    // Refrescar cada 5 minutos si la página está visible
    setInterval(async () => {
        if (!document.hidden && AppState.isOnline) {
            console.log('🔄 Auto-refresh de recomendaciones...');
            await RecommendationsManager.loadAllRecommendations();
            await StatsManager.loadSystemStats();
        }
    }, CONFIG.REFRESH_INTERVAL);
    
    // Refrescar cuando la página vuelve a ser visible
    document.addEventListener('visibilitychange', async () => {
        if (!document.hidden && AppState.lastUpdate) {
            const timeSinceUpdate = Date.now() - AppState.lastUpdate.getTime();
            // Refrescar si han pasado más de 2 minutos
            if (timeSinceUpdate > 120000) {
                await RecommendationsManager.loadAllRecommendations();
                await StatsManager.loadSystemStats();
            }
        }
    });
}

// ================================
// MANEJO DE ERRORES GLOBALES
// ================================

function setupErrorHandling() {
    window.addEventListener('error', (event) => {
        console.error('Error global:', event.error);
        showNotification('Ha ocurrido un error inesperado', 'error');
    });
    
    window.addEventListener('unhandledrejection', (event) => {
        console.error('Promise rejection:', event.reason);
        showNotification('Error de conexión con la API', 'error');
    });
}

// ================================
// INICIALIZACIÓN PRINCIPAL
// ================================

async function initializeApp() {
    console.log('🚀 Inicializando Homepage con API de Recomendaciones...');
    console.log('📍 API URL:', CONFIG.API_BASE_URL);
    
    try {
        // Configurar manejadores de eventos
        setupMobileNavigation();
        setupErrorHandling();
        setupAutoRefresh();
        
        // Verificar conectividad con la API
        console.log('🔗 Verificando conectividad con API...');
        const isConnected = await checkConnectivity();
        console.log('📡 Estado de conexión:', isConnected ? 'CONECTADO' : 'DESCONECTADO');
        
        if (isConnected) {
            // Cargar contenido principal
            console.log('📥 Cargando contenido principal...');
            await Promise.all([
                RecommendationsManager.loadAllRecommendations(),
                StatsManager.loadSystemStats()
            ]);
            
            showNotification('Sistema de recomendaciones cargado correctamente', 'success');
        } else {
            showNotification('Error de conexión con la API de recomendaciones', 'error');
            
            // Intentar cargar datos básicos aunque la API falle
            console.log('⚠️ Modo offline - mostrando interfaz básica');
            
            // Mostrar mensaje de error en las secciones
            ['recent', 'featured', 'popular', 'trending'].forEach(type => {
                UIManager.showError(`${type}-articles`, 
                    `No se pudieron cargar artículos ${type}`, 
                    'Verifique que la API esté funcionando en http://localhost:8000');
            });
        }
        
    } catch (error) {
        console.error('❌ Error inicializando aplicación:', error);
        showNotification('Error inicializando la aplicación', 'error');
        
        // Mostrar detalles del error en consola
        console.error('🔍 Detalles del error:', {
            message: error.message,
            stack: error.stack,
            name: error.name
        });
    }
    
    console.log('✅ Homepage inicializada');
}

// ================================
// INICIO DE LA APLICACIÓN
// ================================

// Inicializar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}