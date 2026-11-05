/**
 * ==============================================================================
 * BusDrex - CLIENTE API REST Y MANEJO DE AUTENTICACIÓN (static/js/api.js)
 * Evaluación 2: Programación Back End | Año: 2026
 * Estudiante: Benjamin Gómez | Sección: AP-N4-C1
 * ==============================================================================
 * Centraliza:
 * 1. Gestión de Tokens JWT (Access y Refresh) en localStorage.
 * 2. Wrapper 'authFetch' con interceptor de autorización y auto-renovación en 401.
 * 3. Actualización dinámica del menú de navegación según rol (Visitante / Pasajero / Admin).
 * 4. Actualización del contador en tiempo real del Carro de Pasajes.
 * 5. Cierre de sesión seguro sincronizado con backend.
 * ==============================================================================
 */

const STORAGE_KEYS = {
    ACCESS: 'busdrex_access_token',
    REFRESH: 'busdrex_refresh_token',
    USER: 'busdrex_user_data'
};

const BusdrexAPI = {
    // --------------------------------------------------------------------------
    // 1. MANEJO DE TOKENS Y ESTADO DE SESIÓN
    // --------------------------------------------------------------------------
    getAccessToken() {
        return localStorage.getItem(STORAGE_KEYS.ACCESS);
    },

    getRefreshToken() {
        return localStorage.getItem(STORAGE_KEYS.REFRESH);
    },

    getUser() {
        try {
            const data = localStorage.getItem(STORAGE_KEYS.USER);
            return data ? JSON.parse(data) : null;
        } catch (e) {
            return null;
        }
    },

    getUserRole() {
        const user = this.getUser();
        return user ? user.rol : null;
    },

    isAdmin() {
        const user = this.getUser();
        return user && (user.rol === 'ADMIN_FLOTA' || user.is_admin_flota === true);
    },

    isPasajero() {
        const user = this.getUser();
        return user && user.rol === 'PASAJERO';
    },

    saveSession(access, refresh, usuario) {
        if (access) localStorage.setItem(STORAGE_KEYS.ACCESS, access);
        if (refresh) localStorage.setItem(STORAGE_KEYS.REFRESH, refresh);
        if (usuario) localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(usuario));
        this.updateNavbar();
    },

    clearSession() {
        localStorage.removeItem(STORAGE_KEYS.ACCESS);
        localStorage.removeItem(STORAGE_KEYS.REFRESH);
        localStorage.removeItem(STORAGE_KEYS.USER);
        this.updateNavbar();
    },

    // --------------------------------------------------------------------------
    // 2. INTERCEPTOR FETCH CON RENOVACIÓN AUTOMÁTICA EN 401
    // --------------------------------------------------------------------------
    async authFetch(url, options = {}) {
        options.headers = options.headers || {};
        
        // Agregar Bearer token si existe
        const token = this.getAccessToken();
        if (token && !options.headers['Authorization']) {
            options.headers['Authorization'] = `Bearer ${token}`;
        }

        if (!options.headers['Content-Type'] && !(options.body instanceof FormData)) {
            options.headers['Content-Type'] = 'application/json';
        }

        let response = await fetch(url, options);

        // Si el token expiró (401), intentar renovar automáticamente con refresh token
        if (response.status === 401 && this.getRefreshToken()) {
            const refreshSuccess = await this.refreshToken();
            if (refreshSuccess) {
                // Reintentar la petición original con el nuevo access token
                options.headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
                response = await fetch(url, options);
            } else {
                // Si la renovación falló, limpiar sesión y redirigir
                this.clearSession();
                if (window.location.pathname.startsWith('/panel') || window.location.pathname.startsWith('/carro')) {
                    window.location.href = `/login/?next=${encodeURIComponent(window.location.pathname)}`;
                }
            }
        }

        return response;
    },

    // --------------------------------------------------------------------------
    // 3. RENOVACIÓN DE TOKEN (POST /api/auth/refresh/)
    // --------------------------------------------------------------------------
    async refreshToken() {
        const refresh = this.getRefreshToken();
        if (!refresh) return false;

        try {
            const res = await fetch('/api/auth/refresh/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.access) {
                    localStorage.setItem(STORAGE_KEYS.ACCESS, data.access);
                    if (data.refresh) localStorage.setItem(STORAGE_KEYS.REFRESH, data.refresh);
                    return true;
                }
            }
        } catch (err) {
            console.error('[BusDrex] Error al renovar token:', err);
        }
        return false;
    },

    // --------------------------------------------------------------------------
    // 4. CIERRE DE SESIÓN SEGURO (POST /api/auth/logout/)
    // --------------------------------------------------------------------------
    async logout() {
        const refresh = this.getRefreshToken();
        try {
            if (refresh) {
                await fetch('/api/auth/logout/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.getAccessToken()}`
                    },
                    body: JSON.stringify({ refresh })
                });
            }
        } catch (e) {
            console.warn('[BusDrex] Error en logout del servidor:', e);
        }

        this.clearSession();
        window.location.href = '/';
    },

    // --------------------------------------------------------------------------
    // 5. ACTUALIZACIÓN DINÁMICA DEL NAVBAR
    // --------------------------------------------------------------------------
    async updateNavbar() {
        const user = this.getUser();
        const navAuth = document.getElementById('navAuthArea');
        const adminLinks = document.querySelectorAll('.admin-only-link');
        const cartBadge = document.getElementById('navCartCount');

        if (!navAuth) return;

        if (user) {
            const roleName = user.rol === 'ADMIN_FLOTA' ? 'Administrador' : 'Pasajero';
            navAuth.innerHTML = `
                <div style="display: flex; align-items: center; gap: 14px;">
                    <a href="/carro/" class="cart-indicator" title="Ver mi carro de compras">
                        🛒 Carro <span class="cart-badge" id="navCartCount">0</span>
                    </a>
                    <div style="display: flex; flex-direction: column; text-align: right; line-height: 1.2;">
                        <span style="font-weight: 700; font-size: 0.9rem; color: #0066cc;">${user.nombre_completo || user.username}</span>
                        <span style="font-size: 0.75rem; color: #64748b; font-weight: 600;">${roleName}</span>
                    </div>
                    <button onclick="BusdrexAPI.logout()" class="btn-login" style="cursor: pointer; background: none;">
                        Salir
                    </button>
                </div>
            `;

            // Mostrar u ocultar enlaces de administrador
            const isAdmin = this.isAdmin();
            adminLinks.forEach(el => {
                el.style.display = isAdmin ? 'inline-block' : 'none';
            });

            // Si es pasajero, actualizar contador del carro
            if (this.isPasajero()) {
                this.updateCartCount();
            }
        } else {
            navAuth.innerHTML = `
                <a href="/login/" class="btn-login">Ingresar</a>
                <a href="/registro/" class="btn-register">Registrarse</a>
            `;
            adminLinks.forEach(el => {
                el.style.display = 'none';
            });
        }
    },

    async updateCartCount() {
        try {
            const res = await this.authFetch('/api/carro-pasajes/');
            if (res.ok) {
                const data = await res.json();
                const badge = document.getElementById('navCartCount');
                if (badge) {
                    badge.textContent = data.cantidad_items || 0;
                }
            }
        } catch (e) {
            // Silencioso
        }
    }
};

// Inicializar navbar al cargar la página
document.addEventListener('DOMContentLoaded', () => {
    BusdrexAPI.updateNavbar();
});
