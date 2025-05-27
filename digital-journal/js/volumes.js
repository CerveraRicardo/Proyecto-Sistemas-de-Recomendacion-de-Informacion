/**
 * VOLUMES.JS - JavaScript para página de volúmenes
 * Conecta directamente con la API para obtener volúmenes de OJS
 * VERSIÓN CORREGIDA - Manejo mejorado de errores y datos
 */

console.log('📄 volumes.js cargado correctamente');

// ================================
// CONFIGURACIÓN
// ================================

const CONFIG = {
    API_BASE_URL: 'http://localhost:8000',
    CACHE_KEY: 'volumes_cache',
    CACHE_DURATION: 300000, // 5 minutos
    RETRY_ATTEMPTS: 3,
    RETRY_DELAY: 2000
};

// ================================
// ESTADO GLOBAL
// ================================

const AppState = {
    volumes: [],
    currentView: 'grid', // 'grid' o 'list'
    isLoading: false,
    isOnline: false,
    lastUpdate: null,
    retryCount: 0
};

console.log('📊 AppState inicializado:', AppState);

// ================================
// UTILIDADES
// ================================

const Utils = {
    formatDate(dateString) {
        if (!dateString) return 'Fecha no disponible';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return 'Fecha no válida';
            
            return date.toLocaleDateString('es-ES', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
        } catch (error) {
            console.warn('Error formateando fecha:', dateString, error);
            return 'Fecha no válida';
        }
    },

    formatYear(year) {
        if (!year) return 'Año no especificado';
        return year.toString();
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

    cleanText(text) {
        if (!text) return '';
        return text.toString().trim().replace(/\s+/g, ' ');
    },

    formatVolumeNumber(volume, number) {
        const vol = volume ? `Vol. ${volume}` : '';
        const num = number ? `Núm. ${number}` : '';
        
        if (vol && num) return `${vol}, ${num}`;
        if (vol) return vol;
        if (num) return num;
        return 'Sin numeración';
    },

    // Cache utilities (solo si localStorage está disponible)
    setCache(key, data) {
        try {
            if (typeof localStorage !== 'undefined') {
                const cacheData = {
                    data: data,
                    timestamp: Date.now()
                };
                localStorage.setItem(key, JSON.stringify(cacheData));
                console.log('💾 Datos guardados en cache');
            }
        } catch (error) {
            console.warn('No se pudo guardar en cache:', error);
        }
    },

    getCache(key) {
        try {
            if (typeof localStorage === 'undefined') return null;
            
            const cached = localStorage.getItem(key);
            if (!cached) return null;

            const cacheData = JSON.parse(cached);
            const isExpired = Date.now() - cacheData.timestamp > CONFIG.CACHE_DURATION;
            
            if (isExpired) {
                localStorage.removeItem(key);
                console.log('🗑️ Cache expirado, removido');
                return null;
            }

            console.log('📦 Datos obtenidos del cache');
            return cacheData.data;
        } catch (error) {
            console.warn('Error leyendo cache:', error);
            return null;
        }
    },

    clearCache() {
        try {
            if (typeof localStorage !== 'undefined') {
                localStorage.removeItem(CONFIG.CACHE_KEY);
                console.log('🗑️ Cache limpiado manualmente');
            }
        } catch (error) {
            console.warn('Error limpiando cache:', error);
        }
    },

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
};

console.log('🛠️ Utils definido');

// ================================
// SERVICIO DE API
// ================================

const ApiService = {
    async request(endpoint, retryCount = 0) {
        const url = `${CONFIG.API_BASE_URL}${endpoint}`;
        
        try {
            console.log(`🔄 API Request (intento ${retryCount + 1}): ${endpoint}`);
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            console.log(`✅ API Response: ${endpoint}`, data);
            return data;
            
        } catch (error) {
            console.error(`❌ API Error (intento ${retryCount + 1}): ${endpoint}`, error);
            
            // Retry logic
            if (retryCount < CONFIG.RETRY_ATTEMPTS - 1) {
                console.log(`🔄 Reintentando en ${CONFIG.RETRY_DELAY}ms...`);
                await Utils.delay(CONFIG.RETRY_DELAY);
                return this.request(endpoint, retryCount + 1);
            }
            
            throw error;
        }
    },

    async getVolumes() {
        return await this.request('/volumes');
    },

    async getVolumeDetails(issueId) {
        return await this.request(`/volumes/${issueId}`);
    },

    async checkHealth() {
        try {
            return await this.request('/health');
        } catch (error) {
            // Fallback al endpoint principal
            try {
                return await this.request('/');
            } catch (fallbackError) {
                throw error;
            }
        }
    }
};

console.log('🌐 ApiService definido');

// ================================
// SISTEMA DE NOTIFICACIONES
// ================================

function showNotification(message, type = 'info', duration = 4000) {
    // Crear o obtener contenedor de notificaciones
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

    const notification = document.createElement('div');
    notification.style.cssText = `
        background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6'};
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

    const icon = type === 'error' ? '⚠️' : type === 'success' ? '✅' : 'ℹ️';
    notification.innerHTML = `${icon} ${Utils.escapeHtml(message)}`;

    container.appendChild(notification);

    // Animar entrada
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 10);

    // Auto-remove
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, duration);
}

// ================================
// MANAGER DE UI
// ================================

const UIManager = {
    showLoading(show = true) {
        const loading = document.getElementById('loading-container');
        const grid = document.getElementById('volumes-grid');
        const list = document.getElementById('volumes-list');
        const error = document.getElementById('error-container');
        const noVolumes = document.getElementById('no-volumes');

        AppState.isLoading = show;

        if (show) {
            loading?.classList.remove('hidden');
            grid?.classList.add('hidden');
            list?.classList.add('hidden');
            error?.classList.add('hidden');
            noVolumes?.classList.add('hidden');
        } else {
            loading?.classList.add('hidden');
        }

        // Animar icono de refresh
        const refreshIcon = document.getElementById('refresh-icon');
        if (refreshIcon) {
            refreshIcon.classList.toggle('fa-spin', show);
        }
    },

    showError(message, details = '') {
        this.showLoading(false);
        
        const error = document.getElementById('error-container');
        const errorMessage = document.getElementById('error-message');
        
        if (errorMessage) {
            errorMessage.innerHTML = Utils.escapeHtml(message);
            if (details) {
                errorMessage.innerHTML += `<br><small style="opacity: 0.8;">${Utils.escapeHtml(details)}</small>`;
            }
        }
        
        error?.classList.remove('hidden');
        document.getElementById('volumes-grid')?.classList.add('hidden');
        document.getElementById('volumes-list')?.classList.add('hidden');
        document.getElementById('no-volumes')?.classList.add('hidden');
    },

    showNoVolumes() {
        this.showLoading(false);
        
        document.getElementById('no-volumes')?.classList.remove('hidden');
        document.getElementById('volumes-grid')?.classList.add('hidden');
        document.getElementById('volumes-list')?.classList.add('hidden');
        document.getElementById('error-container')?.classList.add('hidden');
    },

    showContent() {
        this.showLoading(false);
        
        const grid = document.getElementById('volumes-grid');
        const list = document.getElementById('volumes-list');
        
        if (AppState.currentView === 'grid') {
            grid?.classList.remove('hidden');
            list?.classList.add('hidden');
        } else {
            grid?.classList.add('hidden');
            list?.classList.remove('hidden');
        }
        
        document.getElementById('error-container')?.classList.add('hidden');
        document.getElementById('no-volumes')?.classList.add('hidden');
    },

    updateApiStatus(isOnline, statusText = '') {
        const statusDot = document.getElementById('status-dot');
        const statusTextEl = document.getElementById('status-text');

        AppState.isOnline = isOnline;

        if (statusDot) {
            statusDot.className = `status-dot ${isOnline ? 'online' : 'offline'}`;
        }

        if (statusTextEl) {
            statusTextEl.textContent = statusText || (isOnline ? 'API Conectada' : 'API Desconectada');
        }
    },

    updateVolumeCount(count) {
        const totalElement = document.getElementById('total-volumes');
        if (totalElement) {
            totalElement.textContent = count.toString();
        }
    },

    animateElements(selector, delay = 100) {
        const elements = document.querySelectorAll(selector);
        elements.forEach((el, index) => {
            setTimeout(() => {
                el.style.opacity = '0';
                el.style.transform = 'translateY(20px)';
                el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                
                setTimeout(() => {
                    el.style.opacity = '1';
                    el.style.transform = 'translateY(0)';
                }, 50);
            }, index * delay);
        });
    }
};

console.log('🎨 UIManager definido');

// ================================
// MANAGER DE VOLÚMENES
// ================================

const VolumesManager = {
    renderVolumes(volumes) {
        console.log('🎨 Renderizando volúmenes:', volumes?.length || 0);
        
        UIManager.showLoading(false);
        
        if (!volumes || volumes.length === 0) {
            UIManager.showNoVolumes();
            UIManager.updateVolumeCount(0);
            return;
        }

        // Procesar y validar datos de volúmenes
        const processedVolumes = this.processVolumesData(volumes);

        UIManager.showContent();

        if (AppState.currentView === 'grid') {
            this.renderGridView(processedVolumes);
        } else {
            this.renderListView(processedVolumes);
        }

        UIManager.updateVolumeCount(processedVolumes.length);
        
        // Animar elementos después de renderizar
        setTimeout(() => {
            UIManager.animateElements('.volume-card, .volume-row', 50);
        }, 100);
    },

    processVolumesData(volumes) {
        return volumes.map(volume => ({
            ...volume,
            // Asegurar que los campos críticos tengan valores por defecto
            issue_id: volume.issue_id || 0,
            title: Utils.cleanText(volume.title) || 'Sin título',
            volume: volume.volume || '',
            number: volume.number || '',
            year: volume.year || '',
            date_published: volume.date_published || null,
            articles_count: parseInt(volume.articles_count) || 0,
            description: Utils.cleanText(volume.description) || '',
            journal_title: Utils.cleanText(volume.journal_title) || 'Revista Científica',
            journal_abbreviation: Utils.cleanText(volume.journal_abbreviation) || '',
            access_status: volume.access_status || 'open',
            is_current: Boolean(volume.is_current),
            display_name: volume.display_name || Utils.formatVolumeNumber(volume.volume, volume.number),
            url: volume.url || `/issue/view/${volume.issue_id}`
        }));
    },

    renderGridView(volumes) {
        const grid = document.getElementById('volumes-grid');
        if (!grid) return;
        
        grid.innerHTML = volumes.map(volume => this.createVolumeCard(volume)).join('');
    },

    renderListView(volumes) {
        const list = document.getElementById('volumes-list');
        if (!list) return;
        
        list.innerHTML = volumes.map(volume => this.createVolumeRow(volume)).join('');
    },

    createVolumeCard(volume) {
        const currentBadge = volume.is_current ? '<span class="badge current">Actual</span>' : '';
        const accessBadge = volume.access_status === 'open' ? 
            '<span class="badge open">Acceso Abierto</span>' : 
            '<span class="badge subscription">Suscripción</span>';

        const formattedDate = Utils.formatDate(volume.date_published);
        const year = Utils.formatYear(volume.year);
        const journalName = volume.journal_abbreviation || volume.journal_title;

        return `
            <div class="volume-card ${volume.is_current ? 'current' : ''}" onclick="openVolume(${volume.issue_id})" data-issue-id="${volume.issue_id}">
                <div class="volume-header">
                    <div class="volume-number">${Utils.escapeHtml(volume.display_name)}</div>
                    <div class="volume-badges">
                        ${currentBadge}
                        ${accessBadge}
                    </div>
                </div>
                
                <h3 class="volume-title">${Utils.escapeHtml(volume.title)}</h3>
                
                ${volume.description ? `
                    <p class="volume-description">${Utils.escapeHtml(Utils.truncateText(volume.description, 120))}</p>
                ` : ''}
                
                <div class="volume-meta">
                    <div class="meta-item">
                        <i class="fas fa-calendar"></i>
                        <span>${formattedDate}</span>
                    </div>
                    <div class="meta-item">
                        <i class="fas fa-clock"></i>
                        <span>${year}</span>
                    </div>
                    <div class="meta-item">
                        <i class="fas fa-file-alt"></i>
                        <span>${volume.articles_count} artículo${volume.articles_count !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="meta-item">
                        <i class="fas fa-journal-whills"></i>
                        <span>${Utils.escapeHtml(journalName)}</span>
                    </div>
                </div>
                
                <div class="volume-footer">
                    <span class="articles-count">
                        <i class="fas fa-file-text"></i>
                        ${volume.articles_count} artículo${volume.articles_count !== 1 ? 's' : ''}
                    </span>
                    <button class="view-volume-btn" onclick="event.stopPropagation(); openVolume(${volume.issue_id})" title="Ver volumen completo">
                        <i class="fas fa-eye"></i> Ver volumen
                    </button>
                </div>
            </div>
        `;
    },

    createVolumeRow(volume) {
        const currentBadge = volume.is_current ? '<span class="badge current">Actual</span>' : '';
        const accessBadge = volume.access_status === 'open' ? 
            '<span class="badge open">Abierto</span>' : 
            '<span class="badge subscription">Suscripción</span>';

        const formattedDate = Utils.formatDate(volume.date_published);

        return `
            <div class="volume-row" onclick="openVolume(${volume.issue_id})" data-issue-id="${volume.issue_id}">
                <div class="volume-number">
                    <strong>${Utils.escapeHtml(volume.display_name)}</strong>
                </div>
                <div class="volume-info">
                    <div class="volume-title">${Utils.escapeHtml(volume.title)}</div>
                    <div class="volume-date">${formattedDate}</div>
                </div>
                <div class="volume-articles">
                    ${volume.articles_count} artículo${volume.articles_count !== 1 ? 's' : ''}
                </div>
                <div class="volume-badges">
                    ${currentBadge}
                    ${accessBadge}
                </div>
                <div class="volume-actions">
                    <button class="view-volume-btn" onclick="event.stopPropagation(); openVolume(${volume.issue_id})" title="Ver volumen">
                        <i class="fas fa-eye"></i> Ver
                    </button>
                </div>
            </div>
        `;
    }
};

console.log('📋 VolumesManager definido');

// ================================
// FUNCIONES PRINCIPALES
// ================================

async function loadVolumes(forceReload = false) {
    if (AppState.isLoading) {
        console.log('⏳ Ya hay una carga en proceso, ignorando...');
        return;
    }

    console.log(`📥 Cargando volúmenes... (forceReload: ${forceReload})`);
    
    AppState.isLoading = true;
    AppState.retryCount = 0;
    UIManager.showLoading(true);

    try {
        let volumesData;

        // Intentar cargar desde cache si no es forzado
        if (!forceReload) {
            volumesData = Utils.getCache(CONFIG.CACHE_KEY);
            if (volumesData && volumesData.volumes) {
                console.log('📦 Volúmenes cargados desde cache');
                AppState.volumes = volumesData.volumes;
                VolumesManager.renderVolumes(AppState.volumes);
                return;
            }
        }

        // Limpiar cache si se fuerza la recarga
        if (forceReload) {
            Utils.clearCache();
        }

        // Cargar desde API
        console.log('🌐 Cargando volúmenes desde API...');
        volumesData = await ApiService.getVolumes();
        
        // Validar respuesta de la API
        if (!volumesData) {
            throw new Error('Respuesta vacía de la API');
        }

        if (!volumesData.volumes) {
            console.warn('⚠️ La respuesta no contiene campo "volumes":', volumesData);
            // Intentar usar la respuesta directamente si es un array
            if (Array.isArray(volumesData)) {
                volumesData = { volumes: volumesData };
            } else {
                throw new Error('Formato de respuesta inválido: se esperaba campo "volumes"');
            }
        }

        AppState.volumes = volumesData.volumes || [];
        AppState.lastUpdate = new Date();

        // Guardar en cache
        Utils.setCache(CONFIG.CACHE_KEY, volumesData);

        // Renderizar
        VolumesManager.renderVolumes(AppState.volumes);

        const count = AppState.volumes.length;
        console.log(`✅ ${count} volúmenes cargados exitosamente`);
        
        if (count === 0) {
            showNotification('No se encontraron volúmenes', 'info');
        } else {
            showNotification(`${count} volúmenes cargados`, 'success');
        }

    } catch (error) {
        console.error('❌ Error cargando volúmenes:', error);
        
        AppState.retryCount++;
        
        let errorMessage = 'Error de conexión con la API';
        let errorDetails = error.message;

        // Determinar tipo de error y mensaje específico
        if (error.name === 'AbortError') {
            errorDetails = 'Tiempo de espera agotado - La API no responde';
        } else if (error.message.includes('fetch')) {
            errorDetails = 'No se puede conectar con la API. Verifique que esté ejecutándose en http://localhost:8000';
        } else if (error.message.includes('HTTP 404')) {
            errorDetails = 'Endpoint /volumes no encontrado en la API';
        } else if (error.message.includes('HTTP 500')) {
            errorDetails = 'Error interno del servidor - Verifique la consulta SQL en la API';
        } else if (error.message.includes('JSON')) {
            errorDetails = 'Respuesta inválida de la API - No es JSON válido';
        }

        UIManager.showError(errorMessage, errorDetails);
        showNotification(errorMessage, 'error');

        // Intentar cargar desde cache como fallback
        if (AppState.retryCount === 1) {
            const cachedData = Utils.getCache(CONFIG.CACHE_KEY);
            if (cachedData && cachedData.volumes) {
                console.log('📦 Usando datos en cache como fallback...');
                AppState.volumes = cachedData.volumes;
                VolumesManager.renderVolumes(AppState.volumes);
                showNotification('Mostrando datos en cache', 'info');
            }
        }

    } finally {
        AppState.isLoading = false;
        UIManager.showLoading(false);
    }
}

async function checkConnectivity() {
    try {
        console.log('🔗 Verificando conectividad con API...');
        const response = await ApiService.checkHealth();
        
        let isHealthy = false;
        let statusText = 'Error desconocido';

        if (response) {
            if (response.status === 'healthy') {
                isHealthy = true;
                statusText = 'Sistema saludable';
            } else if (response.message) {
                // Respuesta del endpoint principal
                isHealthy = true;
                statusText = 'API conectada';
            } else {
                statusText = 'Respuesta inválida de la API';
            }
        }

        UIManager.updateApiStatus(isHealthy, statusText);
        console.log(`📡 Estado API: ${isHealthy ? 'SALUDABLE' : 'NO SALUDABLE'} - ${statusText}`);
        return isHealthy;

    } catch (error) {
        console.error('❌ Error verificando conectividad:', error);
        UIManager.updateApiStatus(false, 'Error de conexión');
        return false;
    }
}

// ================================
// FUNCIONES GLOBALES
// ================================

window.setViewMode = function(mode) {
    console.log(`🎨 Cambiando modo de vista a: ${mode}`);
    AppState.currentView = mode;
    
    // Actualizar botones
    const gridBtn = document.getElementById('grid-view-btn');
    const listBtn = document.getElementById('list-view-btn');
    
    if (gridBtn) gridBtn.classList.toggle('active', mode === 'grid');
    if (listBtn) listBtn.classList.toggle('active', mode === 'list');
    
    // Re-renderizar con la nueva vista
    if (AppState.volumes.length > 0) {
        VolumesManager.renderVolumes(AppState.volumes);
    }
    
    showNotification(`Vista cambiada a ${mode === 'grid' ? 'tarjetas' : 'lista'}`, 'info', 2000);
};

window.openVolume = function(issueId) {
    if (!issueId) {
        showNotification('ID de volumen no válido', 'error');
        return;
    }
    
    console.log(`🔗 Abriendo página de detalles del volumen: ${issueId}`);
    
    // Abrir la nueva página de detalles del volumen
    window.location.href = `volume-detail.html?id=${issueId}`;
};

window.loadVolumes = loadVolumes;

// Función para debugging
window.debugVolumes = function() {
    console.log('🐛 DEBUG - Estado actual:', {
        volumes: AppState.volumes,
        isLoading: AppState.isLoading,
        isOnline: AppState.isOnline,
        currentView: AppState.currentView,
        lastUpdate: AppState.lastUpdate,
        retryCount: AppState.retryCount
    });
};

console.log('🌐 Funciones globales definidas');

// ================================
// INICIALIZACIÓN
// ================================

async function initializeApp() {
    console.log('🚀 Inicializando página de volúmenes...');
    console.log('📍 API URL:', CONFIG.API_BASE_URL);
    
    try {
        // Agregar indicador de debug en desarrollo
        if (window.location.hostname === 'localhost') {
            console.log('🔧 Modo desarrollo activado - usa debugVolumes() para debugging');
            window.debugVolumes = window.debugVolumes;
        }

        // Verificar conectividad
        console.log('🔗 Verificando conectividad...');
        const isConnected = await checkConnectivity();
        
        if (isConnected) {
            console.log('✅ API conectada, cargando volúmenes...');
            await loadVolumes();
        } else {
            console.warn('⚠️ API no disponible');
            UIManager.showError(
                'No se puede conectar con la API',
                'Verifique que la API esté ejecutándose en http://localhost:8000 y que el endpoint /volumes esté disponible'
            );
            showNotification('Error de conexión con la API', 'error');
        }
        
    } catch (error) {
        console.error('❌ Error crítico inicializando aplicación:', error);
        UIManager.showError('Error inicializando la aplicación', error.message);
        showNotification('Error inicializando la aplicación', 'error');
    }
    
    console.log('✅ Página de volúmenes inicializada');
}

// ================================
// EVENTOS
// ================================

// Inicializar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    // Si el DOM ya está listo, inicializar inmediatamente
    initializeApp();
}

// Manejar errores globales
window.addEventListener('error', (event) => {
    console.error('❌ Error global:', event.error);
    showNotification('Error inesperado en la página', 'error');
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('❌ Promise rejection:', event.reason);
    showNotification('Error de conexión', 'error');
});

// Manejar cambios de visibilidad para refrescar datos obsoletos
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && AppState.lastUpdate) {
        const timeSinceUpdate = Date.now() - AppState.lastUpdate.getTime();
        // Refrescar si han pasado más de 10 minutos
        if (timeSinceUpdate > 600000) {
            console.log('🔄 Refrescando datos obsoletos...');
            loadVolumes(false); // Permitir cache
        }
    }
});

console.log('📦 volumes.js completamente cargado y configurado');