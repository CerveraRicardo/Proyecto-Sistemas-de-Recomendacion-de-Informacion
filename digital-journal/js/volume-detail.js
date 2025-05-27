/**
 * VOLUME-DETAIL.JS - JavaScript para página de detalles de volumen ACTUALIZADO
 * Conecta con la API para mostrar TODOS los artículos del volumen
 * ACTUALIZADO: Navegación a páginas de artículos individuales
 */

console.log('📄 volume-detail.js cargado correctamente');

// ================================
// CONFIGURACIÓN
// ================================

const CONFIG = {
    API_BASE_URL: 'http://localhost:8000',
    VOLUME_ENDPOINT: '/volumes-no-filter', // Usar endpoint sin filtro de fecha
    RECOMMENDATIONS_ENDPOINT: '/admin/recommendations'
};

// ================================
// ESTADO GLOBAL
// ================================

const AppState = {
    volumeId: null,
    volumeData: null,
    articles: [],
    currentView: 'detailed', // 'detailed' o 'compact'
    currentSort: 'default',
    isLoading: false,
    selectedArticle: null
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

    generateArticleId(article) {
        return `article-${article.publication_id || article.submission_id}`;
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

    updateVolumeHeader(volumeData) {
        // Breadcrumb
        const breadcrumbTitle = document.getElementById('breadcrumb-title');
        if (breadcrumbTitle) {
            breadcrumbTitle.textContent = volumeData.title;
        }

        // Título principal
        const volumeTitle = document.getElementById('volume-title');
        if (volumeTitle) {
            volumeTitle.textContent = volumeData.title;
        }

        // Subtítulo
        const volumeSubtitle = document.getElementById('volume-subtitle');
        if (volumeSubtitle) {
            const subtitle = `Volumen ${volumeData.volume || 'N/A'}, Número ${volumeData.number || 'N/A'} (${volumeData.year || 'N/A'})`;
            volumeSubtitle.textContent = subtitle;
        }

        // Información del volumen
        const publicationDate = document.getElementById('publication-date');
        if (publicationDate) {
            publicationDate.textContent = Utils.formatDate(volumeData.date_published);
        }

        const articlesCount = document.getElementById('articles-count');
        if (articlesCount) {
            articlesCount.textContent = AppState.articles.length;
        }

        // Descripción (si existe)
        if (volumeData.description && volumeData.description.trim()) {
            const volumeDescription = document.getElementById('volume-description');
            const descriptionText = document.getElementById('description-text');
            
            if (volumeDescription && descriptionText) {
                descriptionText.textContent = volumeData.description;
                volumeDescription.style.display = 'block';
            }
        }

        // Actualizar título de la página
        document.title = `${volumeData.title} - Revista Científica`;
    },

    renderArticles() {
        const container = document.getElementById('articles-container');
        const noArticles = document.getElementById('no-articles');
        
        if (!container) return;

        // Aplicar vista actual
        container.className = `articles-container ${AppState.currentView}`;

        if (AppState.articles.length === 0) {
            container.innerHTML = '';
            noArticles.classList.remove('hidden');
            return;
        }

        noArticles.classList.add('hidden');
        
        // Ordenar artículos según configuración actual
        const sortedArticles = this.sortArticles([...AppState.articles]);
        
        // Renderizar artículos
        container.innerHTML = sortedArticles.map((article, index) => 
            this.createArticleCard(article, index + 1)
        ).join('');

        // Animar elementos
        setTimeout(() => {
            const cards = container.querySelectorAll('.article-card');
            cards.forEach((card, index) => {
                setTimeout(() => {
                    card.classList.add('fade-in');
                }, index * 100);
            });
        }, 50);
    },

    createArticleCard(article, number) {
        const cleanTitle = Utils.escapeHtml(article.title || 'Sin título');
        const cleanAuthors = Utils.escapeHtml(article.authors || 'Autor no especificado');
        const cleanAbstract = Utils.cleanHtmlContent(article.abstract);
        const truncatedAbstract = Utils.truncateText(cleanAbstract, 200);
        
        return `
            <div class="article-card" onclick="openArticleDetail(${article.submission_id})" data-article-id="${article.publication_id}">
                <div class="article-header">
                    <div class="article-number">${number}</div>
                    <div class="article-content">
                        <h3 class="article-title">${cleanTitle}</h3>
                        <p class="article-authors">${cleanAuthors}</p>
                        <div class="article-meta">
                            ${article.pages ? `
                                <div class="meta-item">
                                    <i class="fas fa-file-alt"></i>
                                    <span>Páginas ${Utils.escapeHtml(article.pages)}</span>
                                </div>
                            ` : ''}
                            ${article.date_published ? `
                                <div class="meta-item">
                                    <i class="fas fa-calendar"></i>
                                    <span>${Utils.formatDate(article.date_published)}</span>
                                </div>
                            ` : ''}
                            <div class="meta-item">
                                <i class="fas fa-hashtag"></i>
                                <span>ID: ${article.publication_id}</span>
                            </div>
                        </div>
                    </div>
                </div>
                
                ${AppState.currentView === 'detailed' ? `
                    <div class="article-abstract">
                        <p>${Utils.escapeHtml(truncatedAbstract || 'Sin resumen disponible')}</p>
                    </div>
                ` : ''}
                
                <div class="article-actions">
                    <button class="article-btn" onclick="event.stopPropagation(); showArticleDetails(${article.publication_id})" title="Ver detalles">
                        <i class="fas fa-info-circle"></i> Detalles
                    </button>
                    <button class="article-btn primary" onclick="event.stopPropagation(); openArticleDetail(${article.submission_id})" title="Ver artículo completo">
                        <i class="fas fa-eye"></i> Ver artículo
                    </button>
                    <button class="article-btn" onclick="event.stopPropagation(); copyArticleLink(${article.submission_id})" title="Copiar enlace">
                        <i class="fas fa-link"></i> Copiar enlace
                    </button>
                </div>
            </div>
        `;
    },

    sortArticles(articles) {
        switch (AppState.currentSort) {
            case 'title':
                return articles.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
            
            case 'author':
                return articles.sort((a, b) => (a.authors || '').localeCompare(b.authors || ''));
            
            case 'date':
                return articles.sort((a, b) => {
                    const dateA = new Date(a.date_published || '1900-01-01');
                    const dateB = new Date(b.date_published || '1900-01-01');
                    return dateB - dateA; // Más reciente primero
                });
            
            case 'default':
            default:
                // Mantener orden original (seq, luego fecha)
                return articles;
        }
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
// MANAGER DE VOLUMEN
// ================================

const VolumeManager = {
    async loadVolumeData() {
        if (!AppState.volumeId) {
            UIManager.showError('ID de volumen no válido', 'No se proporcionó un ID de volumen válido en la URL');
            return;
        }

        console.log(`🔄 Cargando datos del volumen ${AppState.volumeId}...`);
        UIManager.showLoading(true);

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}${CONFIG.VOLUME_ENDPOINT}/${AppState.volumeId}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            console.log('📊 Datos del volumen recibidos:', data);

            if (data.error) {
                throw new Error(data.error);
            }

            // Guardar datos en el estado
            AppState.volumeData = data.issue;
            AppState.articles = data.articles || [];

            // Actualizar UI
            UIManager.updateVolumeHeader(AppState.volumeData);
            UIManager.renderArticles();
            UIManager.showLoading(false);

            console.log(`✅ Volumen cargado: ${AppState.articles.length} artículos`);

            // Cargar recomendaciones si hay artículos
            if (AppState.articles.length > 0) {
                this.loadRecommendations();
            }

        } catch (error) {
            console.error('❌ Error cargando volumen:', error);
            
            let errorMessage = 'Error cargando el volumen';
            let errorDetails = error.message;

            if (error.message.includes('404')) {
                errorDetails = 'El volumen solicitado no existe o no está publicado';
            } else if (error.message.includes('fetch')) {
                errorDetails = 'No se puede conectar con el servidor. Verifique su conexión a internet.';
            }

            UIManager.showError(errorMessage, errorDetails);
        }
    },

    async loadRecommendations() {
        try {
            const firstArticleId = AppState.articles[0]?.publication_id;
            if (!firstArticleId) return;

            console.log('🔍 Cargando recomendaciones...');
            
            const response = await fetch(`${CONFIG.API_BASE_URL}${CONFIG.RECOMMENDATIONS_ENDPOINT}/${firstArticleId}?limit=4`);
            
            if (response.ok) {
                const data = await response.json();
                if (data.recommendations && data.recommendations.length > 0) {
                    this.renderRecommendations(data.recommendations);
                }
            }
        } catch (error) {
            console.warn('⚠️ No se pudieron cargar recomendaciones:', error);
        }
    },

    renderRecommendations(recommendations) {
        const section = document.getElementById('recommendations-section');
        const grid = document.getElementById('recommendations-grid');
        
        if (!section || !grid || recommendations.length === 0) return;

        grid.innerHTML = recommendations.map(rec => `
            <div class="recommendation-card" onclick="openArticleDetail(${rec.submission_id})">
                <h4>${Utils.escapeHtml(rec.title)}</h4>
                <p class="rec-authors">${Utils.escapeHtml(rec.authors || 'Autor no especificado')}</p>
                <p class="rec-abstract">${Utils.escapeHtml(Utils.truncateText(Utils.cleanHtmlContent(rec.abstract), 100))}</p>
                <div class="rec-score">
                    <i class="fas fa-star"></i>
                    <span>${(rec.similarity_score * 100).toFixed(0)}% similar</span>
                </div>
            </div>
        `).join('');

        section.style.display = 'block';
    }
};

// ================================
// FUNCIONES GLOBALES ACTUALIZADAS
// ================================

window.loadVolumeData = function() {
    VolumeManager.loadVolumeData();
};

window.goBack = function() {
    if (window.history.length > 1) {
        window.history.back();
    } else {
        window.location.href = 'volumes.html';
    }
};

// NUEVA: Función para abrir página de detalles de artículo
window.openArticleDetail = function(articleId) {
    if (articleId) {
        console.log(`🔗 Navegando a detalles del artículo: ${articleId}`);
        window.location.href = `article-detail.html?id=${articleId}`;
    }
};

// Función legacy para abrir en nueva pestaña (sistema OJS)
window.openArticleInNewTab = function(submissionId) {
    if (submissionId) {
        const url = `/article/view/${submissionId}`;
        window.open(url, '_blank');
        console.log(`🔗 Abriendo artículo en nueva pestaña: ${submissionId}`);
    }
};

window.setArticleView = function(view) {
    AppState.currentView = view;
    
    // Actualizar botones
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });
    
    // Re-renderizar artículos
    UIManager.renderArticles();
    
    console.log(`🎨 Vista cambiada a: ${view}`);
};

window.sortArticles = function() {
    const select = document.getElementById('sort-articles');
    AppState.currentSort = select.value;
    UIManager.renderArticles();
    console.log(`📊 Artículos ordenados por: ${AppState.currentSort}`);
};

window.showArticleDetails = function(articleId) {
    const article = AppState.articles.find(a => a.publication_id === articleId);
    if (!article) return;

    AppState.selectedArticle = article;
    
    const modal = document.getElementById('article-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    
    modalTitle.textContent = article.title || 'Sin título';
    
    const cleanAbstract = Utils.cleanHtmlContent(article.abstract);
    
    modalBody.innerHTML = `
        <div class="article-details">
            <div class="detail-section">
                <h4><i class="fas fa-users"></i> Autores</h4>
                <p>${Utils.escapeHtml(article.authors || 'Autor no especificado')}</p>
            </div>
            
            ${article.pages ? `
                <div class="detail-section">
                    <h4><i class="fas fa-file-alt"></i> Páginas</h4>
                    <p>${Utils.escapeHtml(article.pages)}</p>
                </div>
            ` : ''}
            
            ${article.date_published ? `
                <div class="detail-section">
                    <h4><i class="fas fa-calendar"></i> Fecha de publicación</h4>
                    <p>${Utils.formatDate(article.date_published)}</p>
                </div>
            ` : ''}
            
            ${cleanAbstract ? `
                <div class="detail-section">
                    <h4><i class="fas fa-align-left"></i> Resumen</h4>
                    <p style="line-height: 1.6;">${Utils.escapeHtml(cleanAbstract)}</p>
                </div>
            ` : ''}
            
            <div class="detail-section">
                <h4><i class="fas fa-info-circle"></i> Información adicional</h4>
                <p><strong>ID de publicación:</strong> ${article.publication_id}</p>
                <p><strong>ID de envío:</strong> ${article.submission_id}</p>
            </div>
            
            <div class="detail-section">
                <h4><i class="fas fa-external-link-alt"></i> Acciones</h4>
                <div class="modal-action-buttons">
                    <button class="btn primary" onclick="openArticleDetail(${article.submission_id})">
                        <i class="fas fa-eye"></i> Ver Artículo Completo
                    </button>
                    <button class="btn secondary" onclick="copyArticleLink(${article.submission_id})">
                        <i class="fas fa-link"></i> Copiar Enlace
                    </button>
                </div>
            </div>
        </div>
    `;
    
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
};

window.closeArticleModal = function() {
    const modal = document.getElementById('article-modal');
    modal.classList.remove('active');
    document.body.style.overflow = 'auto';
    AppState.selectedArticle = null;
};

window.copyArticleLink = async function(submissionId) {
    const url = `${window.location.origin}/article-detail.html?id=${submissionId}`;
    try {
        await navigator.clipboard.writeText(url);
        showNotification('Enlace copiado al portapapeles', 'success');
    } catch (error) {
        console.error('Error copiando enlace:', error);
        showNotification('Error copiando enlace', 'error');
    }
};

window.scrollToTop = function() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
};

window.downloadVolume = function() {
    showNotification('Función de descarga no implementada', 'info');
};

window.shareVolume = function() {
    if (navigator.share && AppState.volumeData) {
        navigator.share({
            title: AppState.volumeData.title,
            text: `Volumen ${AppState.volumeData.volume}, Número ${AppState.volumeData.number}`,
            url: window.location.href
        }).catch(err => console.log('Error compartiendo:', err));
    } else {
        copyArticleLink(window.location.href);
    }
};

window.citateVolume = function() {
    if (AppState.volumeData) {
        const citation = `Revista Científica, Vol. ${AppState.volumeData.volume}, Núm. ${AppState.volumeData.number} (${AppState.volumeData.year}). ${AppState.volumeData.title}.`;
        
        try {
            navigator.clipboard.writeText(citation);
            showNotification('Cita copiada al portapapeles', 'success');
        } catch (error) {
            showNotification('Error copiando cita', 'error');
        }
    }
};

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
// EVENT LISTENERS
// ================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Inicializando página de detalles de volumen...');
    
    // Obtener ID del volumen de la URL
    AppState.volumeId = Utils.getUrlParameter('id');
    
    if (!AppState.volumeId) {
        UIManager.showError(
            'ID de volumen no especificado', 
            'No se proporcionó un ID de volumen en la URL. Use ?id=VOLUME_ID'
        );
        return;
    }
    
    console.log(`📖 Volume ID: ${AppState.volumeId}`);
    
    // Cargar datos del volumen
    VolumeManager.loadVolumeData();
    
    // Event listeners para scroll
    window.addEventListener('scroll', UIManager.updateScrollFab);
    
    // Event listener para cerrar modal con Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeArticleModal();
        }
    });
    
    // Event listener para cerrar modal haciendo clic fuera
    const articleModal = document.getElementById('article-modal');
    if (articleModal) {
        articleModal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeArticleModal();
            }
        });
    }
    
    console.log('✅ Página de detalles de volumen inicializada');
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
// FUNCIONES DE UTILIDAD ADICIONALES
// ================================

// Función para manejar cambios de vista responsive
function handleResponsiveChanges() {
    const isMobile = window.innerWidth <= 768;
    
    if (isMobile && AppState.currentView === 'detailed') {
        // En móvil, cambiar automáticamente a vista compacta si está en detallada
        setArticleView('compact');
    }
}

// Event listener para cambios de tamaño de ventana
window.addEventListener('resize', handleResponsiveChanges);

// Función para debugging (solo en desarrollo)
if (window.location.hostname === 'localhost') {
    window.debugVolumeState = function() {
        console.log('🐛 Estado actual del volumen:', {
            volumeId: AppState.volumeId,
            volumeData: AppState.volumeData,
            articlesCount: AppState.articles.length,
            currentView: AppState.currentView,
            currentSort: AppState.currentSort,
            isLoading: AppState.isLoading,
            selectedArticle: AppState.selectedArticle
        });
    };
    
    console.log('🔧 Modo desarrollo - usa debugVolumeState() para debugging');
}

console.log('📦 volume-detail.js completamente cargado');