// AI Study Buddy - Login Page Controller

// =============================
// Configuration & Global Variables
// =============================
const API_BASE_URLS = [
    'http://127.0.0.1:5000',
    'http://localhost:5000',
    'http://127.0.0.1:8000',
    'http://localhost:8000'
];

let API_BASE_URL = API_BASE_URLS[0];
let backendConnected = false;

// =============================
// Backend Connection & API
// =============================
async function testBackendConnection() {
    for (const url of API_BASE_URLS) {
        try {
            const response = await fetch(`${url}/health`, { 
                method: 'GET'
            });
            if (response.ok) {
                API_BASE_URL = url;
                console.log(`Backend connected at: ${url}`);
                showNotification('Connected to backend', 'success');
                return true;
            }
        } catch (err) {
            console.log(`Failed to connect to ${url}`);
        }
    }
    console.log('Backend connection failed - running in offline mode');
    showNotification('Running in offline mode', 'info');
    return false;
}

// =============================
// Authentication Functions
// =============================
async function handleLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    
    if (!username || !password) {
        showNotification('Please enter both username and password', 'error');
        return;
    }
    
    const loginBtn = document.getElementById('login-btn');
    const originalContent = loginBtn.innerHTML;
    loginBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Logging in...';
    loginBtn.disabled = true;
    
    try {
        // Simulate authentication delay
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Store user data in localStorage (or sessionStorage)
        const userData = {
            username: username,
            email: `${username.toLowerCase()}@example.com`,
            level: 5,
            xp: 450,
            streak: 7,
            plan: 'Student',
            authToken: 'demo-token-' + Date.now()
        };
        
        localStorage.setItem('ai_study_buddy_user', JSON.stringify(userData));
        localStorage.setItem('ai_study_buddy_token', userData.authToken);
        
        showNotification('Login successful! Redirecting...', 'success');
        
        // Redirect to main app
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1500);
        
    } catch (error) {
        console.error('Login error:', error);
        showNotification('Login failed. Please try again.', 'error');
    } finally {
        loginBtn.innerHTML = originalContent;
        loginBtn.disabled = false;
    }
}

async function handleSignup() {
    const username = document.getElementById('signup-username').value.trim();
    const email = document.getElementById('signup-email').value.trim();
    const password = document.getElementById('signup-password').value;
    
    if (!username || !email || !password) {
        showNotification('Please fill in all fields', 'error');
        return;
    }
    
    if (password.length < 6) {
        showNotification('Password must be at least 6 characters long', 'error');
        return;
    }
    
    const signupBtn = document.getElementById('signup-btn');
    const originalContent = signupBtn.innerHTML;
    signupBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating account...';
    signupBtn.disabled = true;
    
    try {
        // Simulate account creation delay
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        // Store user data
        const userData = {
            username: username,
            email: email,
            level: 1,
            xp: 0,
            streak: 0,
            plan: 'Free',
            authToken: 'demo-token-' + Date.now()
        };
        
        localStorage.setItem('ai_study_buddy_user', JSON.stringify(userData));
        localStorage.setItem('ai_study_buddy_token', userData.authToken);
        
        showNotification('Account created successfully! Redirecting...', 'success');
        
        // Redirect to main app
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1500);
        
    } catch (error) {
        console.error('Signup error:', error);
        showNotification('Account creation failed. Please try again.', 'error');
    } finally {
        signupBtn.innerHTML = originalContent;
        signupBtn.disabled = false;
    }
}

// =============================
// UI Functions
// =============================
function showLogin() {
    document.getElementById('login-form').classList.remove('hidden');
    document.getElementById('signup-form').classList.add('hidden');
    document.getElementById('show-login').classList.add('active');
    document.getElementById('show-signup').classList.remove('active');
}

function showSignup() {
    document.getElementById('login-form').classList.add('hidden');
    document.getElementById('signup-form').classList.remove('hidden');
    document.getElementById('show-login').classList.remove('active');
    document.getElementById('show-signup').classList.add('active');
}

// =============================
// Notification Functions
// =============================
function showNotification(message, type = 'info') {
    // Remove existing notifications
    document.querySelectorAll('.notification').forEach(n => n.remove());
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    const colors = {
        success: '#4CAF50',
        error: '#f44336',
        info: '#2196F3',
        warning: '#ff9800'
    };
    
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${colors[type] || colors.info};
        color: white;
        padding: 15px 25px;
        border-radius: 8px;
        font-weight: 500;
        z-index: 1000;
        transform: translateX(400px);
        transition: transform 0.3s ease;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        max-width: 300px;
    `;
    
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.style.transform = 'translateX(400px)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 5000);
}

// =============================
// Event Listeners Setup
// =============================
function setupEventListeners() {
    // Auth form toggles
    document.getElementById('show-login').addEventListener('click', showLogin);
    document.getElementById('show-signup').addEventListener('click', showSignup);
    document.getElementById('login-btn').addEventListener('click', handleLogin);
    document.getElementById('signup-btn').addEventListener('click', handleSignup);

    // Enter key handlers for forms
    document.getElementById('login-password').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') handleLogin();
    });
    
    document.getElementById('signup-password').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') handleSignup();
    });
}

// =============================
// Check if already logged in
// =============================
function checkExistingAuth() {
    const token = localStorage.getItem('ai_study_buddy_token');
    const userData = localStorage.getItem('ai_study_buddy_user');
    
    if (token && userData) {
        // User is already logged in, redirect to main app
        showNotification('Already logged in, redirecting...', 'info');
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1000);
    }
}

// =============================
// Initialize Login Page
// =============================
async function initializeLoginPage() {
    console.log('Initializing AI Study Buddy Login...');
    
    // Check if user is already logged in
    checkExistingAuth();
    
    // Test backend connection
    backendConnected = await testBackendConnection();
    
    // Setup event listeners
    setupEventListeners();
    
    console.log('Login page initialized successfully!');
}

// =============================
// App Entry Point

// =============================
document.addEventListener('DOMContentLoaded', initializeLoginPage);