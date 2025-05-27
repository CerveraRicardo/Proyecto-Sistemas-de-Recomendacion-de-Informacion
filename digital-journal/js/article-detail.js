/**
 * ARTICLE-DETAIL.JS - JavaScript para página de detalles de artículo
 * Conecta con la API para mostrar información del artículo y recomendaciones
 */

console.log('📄 article-detail.js cargado correctamente');

// ================================
// CONFIGURACIÓN
// ================================

const CONFIG = {
    API_BASE_URL: 'http://localhost:8000',
    ARTICLE_ENDPOINT: '/volumes-no-filter', // Usar endpoint sin filtro para buscar artículo
    RECOMMENDATIONS_ENDPOINT: '/admin/recommendations',
    SIMILAR_LIMIT: 4,
    HYBRID_LIMIT: 4
};

// ================================
// ESTADO GLOBAL
// ================================

const AppState = {
    articleId: null,
    submissionId: null,
    articleData: null,
    similarArticles: [],
    hybridRecommendations: [],
    isLoading: false,
    loadingStates: {
        article: false,
        similar: false,
        hybrid: false
    }
};

// ================================
// UTILIDADES
// ================================

const Utils = {
    getUrlParameter(name) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(name);
    },

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

    truncateText(text, maxLength = 150) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength).trim() + '...';
    },

    cleanHtmlContent(content) {
        if (!content) return '';
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = content;
        const textContent = tempDiv.textContent || tempDiv.innerText || '';
        return textContent.replace(/\s+/g, ' ').trim();
    },

    cleanAuthors(authors) {
        if (!authors) return 'Autor no especificado';
        
        const authorList = authors.split(';')
            .map(author => author.trim())
            .filter(author => author && author.length > 2)
            .filter((author, index, arr) => {
                const cleanAuthor = author.replace(/\s+/g, ' ').toLowerCase();
                return arr.findIndex(a => a.replace(/\s+/g, ' ').toLowerCase() === cleanAuthor) === index;
            })
            .slice(0, 5); // Máximo 5 autores
        
        if (authorList.length === 0) return 'Autor no especificado';
        
        return authorList.join(', ') + (authorList.length >= 5 ? ' et al.' : '');
    },

    generateCitation(article, format = 'apa') {
        if (!article) return '';
        
        const authors = Utils.cleanAuthors(article.authors);
        const title = article.title || 'Sin título';
        const year = article.date_published ? new Date(article.date_published).getFullYear() : 'n.d.';
        const journal = 'Revista Científica';
        
        switch (format) {
            case 'apa':
                return `${authors} (${year}). ${title}. ${journal}.`;
            case 'mla':
                return `${authors}. "${title}." ${journal}, ${year}.`;
            case 'chicago':
                return `${authors}. "${title}." ${journal} (${year}).`;
            default:
                return `${authors} (${year}). ${title}. ${journal}.`;
        }
    }
};

// ================================
// MANAGER DE UI
// ================================

const UIManager = {
    showLoading(show = true) {
        const loading = document.getElementById('loading-container');
        const mainContent = document.getElementById('main-content');
        const errorContainer = document.getElementById('error-container');

        if (show) {
            loading.style.display = 'flex';
            mainContent.style.display = 'none';
            errorContainer.classList.add('hidden');
        } else {
            loading.style.display = 'none';
            mainContent.style.display = 'block';
        }

        AppState.isLoading = show;
    },

    showError(message, details = '') {
        this.showLoading(false);
        
        const errorContainer = document.getElementById('error-container');
        const errorMessage = document.getElementById('error-message');
        
        if (errorMessage) {
            errorMessage.innerHTML = Utils.escapeHtml(message);
            if (details) {
                errorMessage.innerHTML += `<br><small style="opacity: 0.8;">${Utils.escapeHtml(details)}</small>`;
            }
        }
        
        errorContainer.classList.remove('hidden');
        document.getElementById('main-content').style.display = 'none';
    },

    updateArticleHeader(article) {
        // Breadcrumb
        const breadcrumbTitle = document.getElementById('breadcrumb-title');
        if (breadcrumbTitle) {
            breadcrumbTitle.textContent = Utils.truncateText(article.title, 50);
        }

        // Título principal
        const articleTitle = document.getElementById('article-title');
        if (articleTitle) {
            articleTitle.textContent = article.title;
        }

        // Autores
        const articleAuthors = document.getElementById('article-authors');
        if (articleAuthors) {
            const authorsSpan = articleAuthors.querySelector('span');
            if (authorsSpan) {
                authorsSpan.textContent = Utils.cleanAuthors(article.authors);
            }
        }

        // Fecha de publicación
        const publicationDate = document.getElementById('publication-date');
        if (publicationDate) {
            publicationDate.textContent = Utils.formatDate(article.date_published);
        }

        // Páginas
        const articlePages = document.getElementById('article-pages');
        if (articlePages) {
            articlePages.textContent = article.pages || 'No especificado';
        }

        // ID de publicación
        const publicationId = document.getElementById('publication-id');
        if (publicationId) {
            publicationId.textContent = article.publication_id;
        }

        // Actualizar título de la página
        document.title = `${article.title} - Revista Científica`;
    },

    updateArticleContent(article) {
        // Resumen/Abstract
        const abstractContent = document.getElementById('abstract-content');
        if (abstractContent) {
            const cleanAbstract = Utils.cleanHtmlContent(article.abstract);
            if (cleanAbstract) {
                abstractContent.innerHTML = `<p>${Utils.escapeHtml(cleanAbstract)}</p>`;
            } else {
                abstractContent.innerHTML = '<p>No hay resumen disponible para este artículo.</p>';
            }
        }

        // Información de autores (en caso de que haya datos adicionales)
        const authorDetails = document.getElementById('author-details');
        if (authorDetails) {
            const authors = Utils.cleanAuthors(article.authors);
            authorDetails.innerHTML = `<p>${Utils.escapeHtml(authors)}</p>`;
        }

        // Keywords si están disponibles (placeholder por ahora)
        const keywordsSection = document.getElementById('keywords-section');
        if (keywordsSection && article.keywords) {
            keywordsSection.style.display = 'block';
            const keywordsList = document.getElementById('keywords-list');
            if (keywordsList) {
                const keywords = article.keywords.split(',').map(k => k.trim());
                keywordsList.innerHTML = keywords.map(keyword => 
                    `<span class="keyword-tag">${Utils.escapeHtml(keyword)}</span>`
                ).join('');
            }
        }
    },

    setLoadingState(section, isLoading) {
        AppState.loadingStates[section] = isLoading;
        
        const loadingSpinner = document.getElementById(`${section}-loading`);
        if (loadingSpinner) {
            loadingSpinner.style.display = isLoading ? 'inline-block' : 'none';
        }
    },

    renderSimilarArticles(articles) {
        const grid = document.getElementById('similar-articles-grid');
        const noSimilar = document.getElementById('no-similar');
        
        if (!grid) return;

        if (!articles || articles.length === 0) {
            grid.innerHTML = '';
            noSimilar.classList.remove('hidden');
            return;
        }

        noSimilar.classList.add('hidden');
        grid.innerHTML = articles.map(article => this.createRecommendationCard(article, 'similar')).join('');
        
        // Animar elementos
        setTimeout(() => {
            const cards = grid.querySelectorAll('.recommendation-card');
            cards.forEach((card, index) => {
                setTimeout(() => {
                    card.classList.add('fade-in');
                }, index * 100);
            });
        }, 50);
    },

    renderHybridRecommendations(recommendations) {
        const grid = document.getElementById('hybrid-recommendations-grid');
        const noHybrid = document.getElementById('no-hybrid');
        
        if (!grid) return;

        if (!recommendations || recommendations.length === 0) {
            grid.innerHTML = '';
            noHybrid.classList.remove('hidden');
            return;
        }

        noHybrid.classList.add('hidden');
        grid.innerHTML = recommendations.map(rec => this.createRecommendationCard(rec, 'hybrid')).join('');
        
        // Animar elementos
        setTimeout(() => {
            const cards = grid.querySelectorAll('.recommendation-card');
            cards.forEach((card, index) => {
                setTimeout(() => {
                    card.classList.add('fade-in');
                }, index * 100);
            });
        }, 50);
    },

    createRecommendationCard(article, type) {
        const score = article.similarity_score || article.score || 0;
        const algorithm = article.algorithm || (type === 'similar' ? 'Análisis de Contenido' : 'IA Híbrida');
        
        const cleanTitle = Utils.escapeHtml(article.title || 'Sin título');
        const cleanAuthors = Utils.cleanAuthors(article.authors);
        const cleanAbstract = Utils.cleanHtmlContent(article.abstract);
        const truncatedAbstract = Utils.truncateText(cleanAbstract || 'Sin resumen disponible', 100);
        
        // Determinar ID para navegación (submission_id o publication_id)
        const articleId = article.submission_id || article.publication_id;
        
        return `
            <div class="recommendation-card" onclick="openArticleDetail(${articleId})">
                <div class="rec-header">
                    <h4 class="rec-title">${cleanTitle}</h4>
                    <div class="rec-score">
                        <i class="fas fa-star"></i>
                        <span>${(score * 100).toFixed(0)}%</span>
                    </div>
                </div>
                
                <div class="rec-authors">
                    <i class="fas fa-users"></i>
                    <span>${Utils.escapeHtml(cleanAuthors)}</span>
                </div>
                
                <div class="rec-abstract">
                    <p>${Utils.escapeHtml(truncatedAbstract)}</p>
                </div>
                
                <div class="rec-footer">
                    <div class="rec-algorithm">
                        <i class="fas fa-brain"></i>
                        <span>${algorithm}</span>
                    </div>
                    <button class="rec-btn" onclick="event.stopPropagation(); openArticleDetail(${articleId})" title="Ver artículo">
                        <i class="fas fa-arrow-right"></i>
                    </button>
                </div>
            </div>
        `;
    },

    updateScrollFab() {
        const fab = document.getElementById('scroll-top-fab');
        if (window.scrollY > 300) {
            fab.classList.add('visible');
        } else {
            fab.classList.remove('visible');
        }
    }
};

// ================================
// MANAGER DE ARTÍCULOS
// ================================

const ArticleManager = {
    async loadArticleData() {
        if (!AppState.submissionId) {
            UIManager.showError('ID de artículo no válido', 'No se proporcionó un ID de artículo válido en la URL');
            return;
        }

        console.log(`🔄 Cargando datos del artículo ${AppState.submissionId}...`);
        UIManager.showLoading(true);
        UIManager.setLoadingState('article', true);

        try {
            // Buscar el artículo en todos los volúmenes
            const article = await this.findArticleInVolumes(AppState.submissionId);
            
            if (!article) {
                throw new Error('Artículo no encontrado');
            }

            // Guardar datos en el estado
            AppState.articleData = article;
            AppState.articleId = article.publication_id;

            // Actualizar UI
            UIManager.updateArticleHeader(article);
            UIManager.updateArticleContent(article);
            UIManager.showLoading(false);

            console.log(`✅ Artículo cargado exitosamente`);

            // Cargar recomendaciones en paralelo
            await Promise.all([
                this.loadSimilarArticles(),
                this.loadHybridRecommendations()
            ]);

        } catch (error) {
            console.error('❌ Error cargando artículo:', error);
            
            let errorMessage = 'Error cargando el artículo';
            let errorDetails = error.message;

            if (error.message.includes('404') || error.message.includes('no encontrado')) {
                errorDetails = 'El artículo solicitado no existe o no está publicado';
            } else if (error.message.includes('fetch')) {
                errorDetails = 'No se puede conectar con el servidor. Verifique su conexión a internet.';
            }

            UIManager.showError(errorMessage, errorDetails);
        } finally {
            UIManager.setLoadingState('article', false);
        }
    },

    async findArticleInVolumes(submissionId) {
        try {
            // Primero intentar obtener todos los volúmenes
            const volumesResponse = await fetch(`${CONFIG.API_BASE_URL}/volumes`);
            
            if (!volumesResponse.ok) {
                throw new Error('Error obteniendo lista de volúmenes');
            }

            const volumesData = await volumesResponse.json();
            const volumes = volumesData.volumes || [];

            console.log(`🔍 Buscando artículo en ${volumes.length} volúmenes...`);

            // Buscar el artículo en cada volumen
            for (const volume of volumes) {
                try {
                    const volumeResponse = await fetch(`${CONFIG.API_BASE_URL}/volumes-no-filter/${volume.issue_id}`);
                    
                    if (volumeResponse.ok) {
                        const volumeData = await volumeResponse.json();
                        const articles = volumeData.articles || [];
                        
                        // Buscar por submission_id
                        const foundArticle = articles.find(article => 
                            article.submission_id == submissionId || article.publication_id == submissionId
                        );
                        
                        if (foundArticle) {
                            console.log(`✅ Artículo encontrado en volumen ${volume.issue_id}`);
                            return foundArticle;
                        }
                    }
                } catch (volumeError) {
                    console.warn(`⚠️ Error buscando en volumen ${volume.issue_id}:`, volumeError);
                    continue;
                }
            }

            return null;

        } catch (error) {
            console.error('❌ Error en búsqueda de artículo:', error);
            throw error;
        }
    },

    async loadSimilarArticles() {
        if (!AppState.articleData || !AppState.articleData.publication_id) {
            console.warn('⚠️ No hay datos de artículo para cargar recomendaciones similares');
            return;
        }

        console.log('🔍 Cargando artículos similares...');
        UIManager.setLoadingState('similar', true);

        try {
            const response = await fetch(
                `${CONFIG.API_BASE_URL}${CONFIG.RECOMMENDATIONS_ENDPOINT}/${AppState.articleData.publication_id}?limit=${CONFIG.SIMILAR_LIMIT}`
            );
            
            if (response.ok) {
                const data = await response.json();
                const recommendations = data.recommendations || [];
                
                console.log(`✅ ${recommendations.length} artículos similares encontrados`);
                
                AppState.similarArticles = recommendations;
                UIManager.renderSimilarArticles(recommendations);
            } else {
                console.warn('⚠️ No se pudieron cargar artículos similares:', response.status);
                UIManager.renderSimilarArticles([]);
            }

        } catch (error) {
            console.error('❌ Error cargando artículos similares:', error);
            UIManager.renderSimilarArticles([]);
        } finally {
            UIManager.setLoadingState('similar', false);
        }
    },

    async loadHybridRecommendations() {
        console.log('🧠 Cargando recomendaciones híbridas...');
        UIManager.setLoadingState('hybrid', true);

        try {
            // Por ahora, simulamos recomendaciones híbridas usando las recientes
            // En el futuro se puede implementar un endpoint específico para híbridas
            const response = await fetch(`${CONFIG.API_BASE_URL}/admin/homepage/featured?limit=${CONFIG.HYBRID_LIMIT}`);
            
            if (response.ok) {
                const data = await response.json();
                const recommendations = data.articles || [];
                
                // Filtrar el artículo actual si está en las recomendaciones
                const filteredRecs = recommendations.filter(rec => 
                    rec.submission_id != AppState.submissionId && 
                    rec.publication_id != AppState.articleId
                );
                
                console.log(`✅ ${filteredRecs.length} recomendaciones híbridas encontradas`);
                
                AppState.hybridRecommendations = filteredRecs;
                UIManager.renderHybridRecommendations(filteredRecs);
            } else {
                console.warn('⚠️ No se pudieron cargar recomendaciones híbridas:', response.status);
                UIManager.renderHybridRecommendations([]);
            }

        } catch (error) {
            console.error('❌ Error cargando recomendaciones híbridas:', error);
            UIManager.renderHybridRecommendations([]);
        } finally {
            UIManager.setLoadingState('hybrid', false);
        }
    }
};

// ================================
// FUNCIONES GLOBALES
// ================================

window.loadArticleData = function() {
    ArticleManager.loadArticleData();
};

window.goBack = function() {
    if (window.history.length > 1) {
        window.history.back();
    } else {
        window.location.href = 'index.html';
    }
};

window.openArticle = function(articleId) {
    if (articleId) {
        // Navegar a la página de detalles del artículo
        window.location.href = `article-detail.html?id=${articleId}`;
    }
};

// Funciones de artículo removidas - botones eliminados

window.loadSimilarArticles = function() {
    ArticleManager.loadSimilarArticles();
};

window.loadHybridRecommendations = function() {
    ArticleManager.loadHybridRecommendations();
};

window.scrollToTop = function() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
};

// Funciones relacionadas con modal de citas removidas

// ================================
// SISTEMA DE NOTIFICACIONES
// ================================

function showNotification(message, type = 'info', duration = 3000) {
    const container = getOrCreateNotificationContainer();
    const notificationId = `notification-${Date.now()}`;
    
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
    
    // Estilos inline para las notificaciones
    notification.style.cssText = `
        background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : type === 'warning' ? '#f59e0b' : '#3b82f6'};
        color: white;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        display: flex;
        align-items: center;
        gap: 8px;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    `;
    
    container.appendChild(notification);
    
    // Animar entrada
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 10);
    
    // Auto-remove
    setTimeout(() => removeNotification(notificationId), duration);
}

function removeNotification(notificationId) {
    const notification = document.getElementById(notificationId);
    if (notification) {
        notification.style.transform = 'translateX(100%)';
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
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            max-width: 400px;
        `;
        document.body.appendChild(container);
    }
    return container;
}

// ================================
// UTILIDADES ADICIONALES
// ================================

function copyToClipboard(text) {
    try {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text);
        } else {
            // Fallback para navegadores que no soportan clipboard API
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
        }
    } catch (error) {
        console.error('Error copiando al portapapeles:', error);
    }
}

// ================================
// EVENT LISTENERS
// ================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Inicializando página de detalles de artículo...');
    
    // Obtener ID del artículo de la URL
    AppState.submissionId = Utils.getUrlParameter('id');
    
    if (!AppState.submissionId) {
        UIManager.showError(
            'ID de artículo no especificado', 
            'No se proporcionó un ID de artículo en la URL. Use ?id=ARTICLE_ID'
        );
        return;
    }
    
    console.log(`📖 Article ID: ${AppState.submissionId}`);
    
    // Cargar datos del artículo
    ArticleManager.loadArticleData();
    
    // Event listeners para scroll
    window.addEventListener('scroll', UIManager.updateScrollFab);
    
    // Event listener para cerrar modal con Escape - removido (sin modal de citas)
    
    console.log('✅ Página de detalles de artículo inicializada');
});

// ================================
// MANEJO DE ERRORES GLOBALES
// ================================

window.addEventListener('error', (event) => {
    console.error('❌ Error global:', event.error);
    showNotification('Ha ocurrido un error inesperado', 'error');
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('❌ Promise rejection:', event.reason);
    showNotification('Error de conexión', 'error');
});

// ================================
// FUNCIONES DE DEBUGGING
// ================================

if (window.location.hostname === 'localhost') {
    window.debugArticleState = function() {
        console.log('🐛 Estado actual del artículo:', {
            articleId: AppState.articleId,
            submissionId: AppState.submissionId,
            articleData: AppState.articleData,
            similarArticles: AppState.similarArticles,
            hybridRecommendations: AppState.hybridRecommendations,
            loadingStates: AppState.loadingStates
        });
    };
    
    console.log('🔧 Modo desarrollo - usa debugArticleState() para debugging');
}

console.log('📦 article-detail.js completamente cargado');