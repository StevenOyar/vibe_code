// =============================
// AI Study Buddy - Fixed Frontend Controller
// =============================

document.addEventListener('DOMContentLoaded', initializeApp);

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
let currentUser = null;
let authToken = null; // Using in-memory storage instead of localStorage
let backendConnected = false;


// Application State
let currentCards = [];
let savedCards = [];
let generatedCards = [];
let currentSection = 'home'; // Start with home section
let timetableItems = [];
let todoItems = [];

// Study Session State
let studySession = {
    active: false,
    startTime: null,
    currentCard: 0,
    cardsStudied: 0,
    correctAnswers: 0,
    cards: [],
    timer: null,
    sessionTime: 0
};

// Gamification
let userStats = {
    level: 1,
    xp: 0,
    streak: 0,
    totalCards: 0
};

// XP Values by difficulty
const XP_VALUES = {
    easy: 3,
    medium: 5,
    hard: 8
};

// Sample data for offline mode
const sampleQuestions = {
    math: [
        { question: "What is the Pythagorean theorem?", answer: "a² + b² = c², where c is the hypotenuse of a right triangle.", difficulty: "medium" },
        { question: "What is the quadratic formula?", answer: "x = [-b ± √(b² - 4ac)] / (2a)", difficulty: "hard" },
        { question: "What is 2 + 2?", answer: "4", difficulty: "easy" }
    ],
    english: [
        { question: "What is a metaphor?", answer: "A figure of speech that describes an object or action in a way that isn't literally true.", difficulty: "medium" },
        { question: "What are the three main types of irony?", answer: "Verbal, situational, and dramatic irony.", difficulty: "hard" },
        { question: "What is a noun?", answer: "A word that names a person, place, thing, or idea.", difficulty: "easy" }
    ],
    spanish: [
        { question: "How do you say 'hello' in Spanish?", answer: "Hola", difficulty: "easy" },
        { question: "What is the difference between 'ser' and 'estar'?", answer: "Both mean 'to be', but 'ser' is for permanent traits and 'estar' for temporary states.", difficulty: "hard" },
        { question: "How do you say 'thank you' in Spanish?", answer: "Gracias", difficulty: "easy" }
    ],
    german: [
        { question: "How do you say 'thank you' in German?", answer: "Danke", difficulty: "easy" },
        { question: "What are the three German articles?", answer: "Der (masculine), die (feminine), das (neuter)", difficulty: "medium" },
        { question: "How do you say 'good morning' in German?", answer: "Guten Morgen", difficulty: "easy" }
    ],
    science: [
        { question: "What is photosynthesis?", answer: "The process by which plants convert light energy into chemical energy.", difficulty: "medium" },
        { question: "What are the three states of matter?", answer: "Solid, liquid, and gas.", difficulty: "easy" },
        { question: "What is DNA?", answer: "Deoxyribonucleic acid - the molecule that carries genetic information.", difficulty: "hard" }
    ],
    history: [
        { question: "When did World War II end?", answer: "1945", difficulty: "easy" },
        { question: "Who was the first president of the United States?", answer: "George Washington", difficulty: "easy" },
        { question: "What was the Renaissance?", answer: "A period of cultural rebirth in Europe from the 14th to 17th centuries.", difficulty: "medium" }
    ]
};

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

function getAuthHeaders() {
    return authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
}

async function makeAPICall(endpoint, options = {}) {
    if (!backendConnected) {
        throw new Error('Backend not connected');
    }
    
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders()
        }
    };
    
    const finalOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, finalOptions);
        
        if (!response.ok) {
            let errorMessage;
            try {
                const errorData = await response.json();
                errorMessage = errorData.error || `HTTP error! status: ${response.status}`;
            } catch {
                errorMessage = `HTTP error! status: ${response.status}`;
            }
            throw new Error(errorMessage);
        }
        
        return await response.json();
    } catch (error) {
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            throw new Error('Cannot connect to backend');
        }
        throw error;
    }
}

// =============================
// Authentication Functions - FIXED
// =============================
function checkAuthStatus() {
    // Simulate authentication for demo - no localStorage used
    simulateLogin('Steven');
    return true;
}

function simulateLogin(username = 'Steven') {
    currentUser = {
        username: username,
        email: `${username.toLowerCase()}@example.com`,
        level: 5,
        xp: 450,
        streak: 7,
        plan: 'Student'
    };
    
    userStats = {
        level: currentUser.level,
        xp: currentUser.xp,
        streak: currentUser.streak,
        totalCards: savedCards.length + generatedCards.length
    };
    
    authToken = 'demo-token';
    updateUIForAuthState();
    updateUserDashboard();
    return true;
}

function handleLogout() {
    authToken = null;
    currentUser = null;
    currentCards = [];
    generatedCards = [];
    savedCards = [];
    
    // Reset user stats
    userStats = {
        level: 1,
        xp: 0,
        streak: 0,
        totalCards: 0
    };
    
    showNotification('Logged out successfully', 'info');
    updateUIForAuthState();
    switchSection('home');
}

// =============================
// UI State Management - FIXED
// =============================
function updateUIForAuthState() {
    if (!currentUser) return;
    
    const elements = {
        userDashboard: document.getElementById('user-dashboard'),
        levelProgress: document.getElementById('level-progress-container'),
        logoutBtn: document.getElementById('logout-btn'),
        userWelcome: document.getElementById('user-welcome'),
        usernameDisplay: document.getElementById('username-display'),
        userPlanNav: document.getElementById('user-plan-nav')
    };
    
    // Check if elements exist before manipulating them
    if (elements.userDashboard) elements.userDashboard.classList.remove('hidden');
    if (elements.levelProgress) elements.levelProgress.classList.remove('hidden');
    if (elements.logoutBtn) elements.logoutBtn.classList.remove('hidden');
    if (elements.userWelcome) elements.userWelcome.classList.remove('hidden');
    if (elements.usernameDisplay) elements.usernameDisplay.textContent = currentUser.username;
    if (elements.userPlanNav) elements.userPlanNav.textContent = currentUser.plan;
}

function updateUserDashboard() {
    if (!currentUser) return;
    
    const elements = {
        userLevel: document.getElementById('user-level'),
        userXp: document.getElementById('user-xp'),
        currentStreak: document.getElementById('current-streak'),
        totalCards: document.getElementById('total-cards'),
        userPlan: document.getElementById('user-plan'),
        levelProgressFill: document.getElementById('level-progress-fill'),
        currentLevel: document.getElementById('current-level'),
        nextLevel: document.getElementById('next-level'),
        xpToNext: document.getElementById('xp-to-next')
    };
    
    // Update elements only if they exist
    if (elements.userLevel) elements.userLevel.textContent = userStats.level;
    if (elements.userXp) elements.userXp.textContent = userStats.xp;
    if (elements.currentStreak) elements.currentStreak.textContent = userStats.streak;
    if (elements.totalCards) elements.totalCards.textContent = userStats.totalCards;
    if (elements.userPlan) elements.userPlan.textContent = currentUser.plan;
    
    // Update level progress
    const currentLevelXP = userStats.xp % 100;
    const progressPercentage = (currentLevelXP / 100) * 100;
    
    if (elements.levelProgressFill) elements.levelProgressFill.style.width = `${progressPercentage}%`;
    if (elements.currentLevel) elements.currentLevel.textContent = userStats.level;
    if (elements.nextLevel) elements.nextLevel.textContent = userStats.level + 1;
    if (elements.xpToNext) elements.xpToNext.textContent = 100 - currentLevelXP;
}

function switchSection(sectionName) {
    currentSection = sectionName;
    
    // Update nav tabs safely
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    const targetTab = document.querySelector(`[data-section="${sectionName}"]`);
    if (targetTab) {
        targetTab.classList.add('active');
    }
    
    // Update content sections safely
    document.querySelectorAll('.content-section').forEach(section => {
        section.classList.remove('active');
    });
    
    const targetSection = document.getElementById(`${sectionName}-section`);
    if (targetSection) {
        targetSection.classList.add('active');
    }
    
    // Load section-specific content
    if (sectionName === 'groups') {
        loadGroups();
    } else if (sectionName === 'progress') {
        loadProgressStats();
    } else if (sectionName === 'timetable') {
        loadTimetable();
    }
}

// =============================
// Flashcard Creation & Management - FIXED
// =============================
async function generateAIFlashcards() {
    const notesInput = document.getElementById('notes-input');
    const subjectSelect = document.getElementById('subject-select');
    const difficultySelect = document.getElementById('difficulty-select');
    const groupNameInput = document.getElementById('group-name');
    
    if (!notesInput || !subjectSelect || !difficultySelect) {
        showNotification('Form elements not found!', 'error');
        return;
    }
    
    const notes = notesInput.value.trim();
    const subject = subjectSelect.value;
    const difficulty = difficultySelect.value;
    const groupName = groupNameInput ? groupNameInput.value.trim() : '';
    
    if (!notes) {
        showNotification('Please enter some study notes first!', 'error');
        return;
    }
    
    const generateBtn = document.getElementById('generate-ai-btn');
    if (generateBtn) {
        const originalContent = generateBtn.innerHTML;
        generateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
        generateBtn.disabled = true;
        
        try {
            // Simulate AI generation with sample data
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            const flashcards = generateSampleCards(subject, difficulty, 5);
            
            // Clear previously generated cards
            clearGeneratedCards();
            
            // Create new cards
            generatedCards = flashcards;
            displayGeneratedCards(flashcards);
            
            showNotification(`Generated ${flashcards.length} flashcards!`, 'success');
            
        } catch (error) {
            console.error('Generate flashcards error:', error);
            showNotification(`Error: ${error.message}`, 'error');
        } finally {
            generateBtn.innerHTML = originalContent;
            generateBtn.disabled = false;
        }
    }
}

function generateSampleCards(subject, difficulty, count = 3) {
    const subjectQuestions = sampleQuestions[subject] || sampleQuestions.math;
    const filteredQuestions = subjectQuestions.filter(q => q.difficulty === difficulty);
    const questionsToUse = filteredQuestions.length >= count ? 
        filteredQuestions.slice(0, count) : 
        subjectQuestions.slice(0, count);
    
    return questionsToUse.map(q => ({
        id: Date.now() + Math.random(),
        question: q.question,
        answer: q.answer,
        subject,
        difficulty
    }));
}

function addManualCard() {
    const questionInput = document.getElementById('manual-question');
    const answerInput = document.getElementById('manual-answer');
    const subjectSelect = document.getElementById('subject-select');
    const difficultySelect = document.getElementById('difficulty-select');
    
    if (!questionInput || !answerInput || !subjectSelect || !difficultySelect) {
        showNotification('Form elements not found!', 'error');
        return;
    }
    
    const question = questionInput.value.trim();
    const answer = answerInput.value.trim();
    const subject = subjectSelect.value;
    const difficulty = difficultySelect.value;
    
    if (!question || !answer) {
        showNotification('Please enter both question and answer', 'error');
        return;
    }
    
    const card = { 
        id: Date.now(),
        question, 
        answer, 
        subject, 
        difficulty 
    };
    generatedCards.push(card);
    
    // Add to display
    displayGeneratedCards(generatedCards);
    
    // Clear manual inputs
    questionInput.value = '';
    answerInput.value = '';
    
    showNotification('Manual flashcard added!', 'success');
    updatePreviewCard();
}

async function saveAllCards() {
    if (generatedCards.length === 0) {
        showNotification('No cards to save! Generate or create some first.', 'error');
        return;
    }
    
    const saveBtn = document.getElementById('save-cards-btn');
    if (!saveBtn) {
        showNotification('Save button not found!', 'error');
        return;
    }
    
    const originalContent = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    saveBtn.disabled = true;
    
    try {
        // Simulate saving
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Save locally
        savedCards = [...savedCards, ...generatedCards];
        
        // Award XP
        const totalXP = generatedCards.reduce((sum, card) => sum + XP_VALUES[card.difficulty], 0);
        awardXP(totalXP, 'Cards saved!');
        
        showNotification(`Successfully saved ${generatedCards.length} flashcards!`, 'success');
        
        // Clear generated cards
        generatedCards = [];
        clearGeneratedCards();
        
    } catch (error) {
        console.error('Save cards error:', error);
        showNotification(`Error saving cards: ${error.message}`, 'error');
    } finally {
        saveBtn.innerHTML = originalContent;
        saveBtn.disabled = false;
    }
}

function clearAllCards() {
    generatedCards = [];
    clearGeneratedCards();
    
    const elements = {
        notesInput: document.getElementById('notes-input'),
        manualQuestion: document.getElementById('manual-question'),
        manualAnswer: document.getElementById('manual-answer'),
        groupName: document.getElementById('group-name')
    };
    
    if (elements.notesInput) elements.notesInput.value = '';
    if (elements.manualQuestion) elements.manualQuestion.value = '';
    if (elements.manualAnswer) elements.manualAnswer.value = '';
    if (elements.groupName) elements.groupName.value = '';
    
    showNotification('All cards cleared!', 'info');
    updatePreviewCard();
}

function clearGeneratedCards() {
    const container = document.getElementById('cards-container');
    const generatedSection = document.getElementById('generated-cards');
    
    if (container) container.innerHTML = '';
    if (generatedSection) generatedSection.classList.add('hidden');
}

function displayGeneratedCards(cards) {
    const container = document.getElementById('cards-container');
    const generatedSection = document.getElementById('generated-cards');
    
    if (!container || !generatedSection) return;
    
    container.innerHTML = '';
    
    cards.forEach((card, index) => {
        displaySingleCard(card, index);
    });
    
    generatedSection.classList.remove('hidden');
}

function displaySingleCard(card, index) {
    const container = document.getElementById('cards-container');
    if (!container) return;
    
    const xpValue = XP_VALUES[card.difficulty];
    
    const cardElement = document.createElement('div');
    cardElement.className = 'flashcard';
    cardElement.innerHTML = `
        <div class="flashcard-inner">
            <div class="flashcard-front">
                <div class="xp-badge">${xpValue} XP</div>
                <div class="difficulty-badge difficulty-${card.difficulty}">${card.difficulty.charAt(0).toUpperCase() + card.difficulty.slice(1)}</div>
                <i class="fas fa-question-circle" style="font-size: 2rem; margin-bottom: 15px;"></i>
                <p>${card.question}</p>
            </div>
            <div class="flashcard-back">
                <div class="xp-badge">${xpValue} XP</div>
                <div class="difficulty-badge difficulty-${card.difficulty}">${card.difficulty.charAt(0).toUpperCase() + card.difficulty.slice(1)}</div>
                <i class="fas fa-lightbulb" style="font-size: 2rem; margin-bottom: 15px;"></i>
                <p>${card.answer}</p>
            </div>
        </div>
        <div class="card-actions" style="margin-top: 10px; text-align: center;">
            <button class="btn btn-danger" onclick="removeGeneratedCard(${index})" style="padding: 5px 10px; font-size: 0.8rem;">
                <i class="fas fa-trash"></i> Remove
            </button>
        </div>
    `;
    
    // Add flip functionality
    cardElement.addEventListener('click', (e) => {
        if (!e.target.closest('.card-actions')) {
            cardElement.classList.toggle('flipped');
        }
    });
    
    container.appendChild(cardElement);
}

function removeGeneratedCard(index) {
    generatedCards.splice(index, 1);
    displayGeneratedCards(generatedCards);
    showNotification('Card removed!', 'info');
}

function updatePreviewCard() {
    const elements = {
        manualQuestion: document.getElementById('manual-question'),
        manualAnswer: document.getElementById('manual-answer'),
        difficultySelect: document.getElementById('difficulty-select'),
        previewQuestion: document.getElementById('preview-question'),
        previewAnswer: document.getElementById('preview-answer'),
        previewFlashcard: document.getElementById('preview-flashcard')
    };
    
    if (!elements.previewQuestion || !elements.previewAnswer) return;
    
    const question = elements.manualQuestion ? elements.manualQuestion.value.trim() : '';
    const answer = elements.manualAnswer ? elements.manualAnswer.value.trim() : '';
    const difficulty = elements.difficultySelect ? elements.difficultySelect.value : 'medium';
    const xpValue = XP_VALUES[difficulty];
    
    elements.previewQuestion.textContent = question || "Click 'Generate with AI' or add a manual question to see preview";
    elements.previewAnswer.textContent = answer || "Answer will appear here";
    
    // Update XP and difficulty badges safely
    if (elements.previewFlashcard) {
        const xpBadges = elements.previewFlashcard.querySelectorAll('.xp-badge');
        const difficultyBadges = elements.previewFlashcard.querySelectorAll('.difficulty-badge');
        
        xpBadges.forEach(badge => badge.textContent = `${xpValue} XP`);
        
        difficultyBadges.forEach(badge => {
            badge.className = `difficulty-badge difficulty-${difficulty}`;
            badge.textContent = difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
        });
    }
}

// =============================
// Study Session Functions - FIXED
// =============================
async function startStudySession() {
    let studyCards = [...savedCards, ...generatedCards];
    
    // Fallback to sample cards if no cards available
    if (studyCards.length === 0) {
        studyCards = [];
        Object.keys(sampleQuestions).forEach(subject => {
            studyCards.push(...sampleQuestions[subject].map(q => ({...q, subject})));
        });
    }
    
    if (studyCards.length === 0) {
        showNotification('No flashcards available for study! Create some first.', 'error');
        return;
    }
    
    // Initialize session
    studySession = {
        active: true,
        startTime: Date.now(),
        currentCard: 0,
        cardsStudied: 0,
        correctAnswers: 0,
        cards: studyCards,
        sessionTime: 0
    };
    
    // Start timer
    studySession.timer = setInterval(updateSessionTimer, 1000);
    
    // Update UI safely
    const elements = {
        startBtn: document.getElementById('start-session-btn'),
        pauseBtn: document.getElementById('pause-session-btn'),
        endBtn: document.getElementById('end-session-btn'),
        reviewInterface: document.getElementById('review-interface')
    };
    
    if (elements.startBtn) elements.startBtn.classList.add('hidden');
    if (elements.pauseBtn) elements.pauseBtn.classList.remove('hidden');
    if (elements.endBtn) elements.endBtn.classList.remove('hidden');
    if (elements.reviewInterface) elements.reviewInterface.classList.remove('hidden');
    
    showCurrentCard();
    showNotification('Study session started!', 'success');
}

function pauseStudySession() {
    const pauseBtn = document.getElementById('pause-session-btn');
    if (!pauseBtn) return;
    
    if (studySession.timer) {
        clearInterval(studySession.timer);
        studySession.timer = null;
    }
    
    if (pauseBtn.innerHTML.includes('Pause')) {
        pauseBtn.innerHTML = '<i class="fas fa-play"></i> Resume';
        showNotification('Study session paused', 'info');
    } else {
        studySession.timer = setInterval(updateSessionTimer, 1000);
        pauseBtn.innerHTML = '<i class="fas fa-pause"></i> Pause';
        showNotification('Study session resumed', 'info');
    }
}

function endStudySession() {
    if (studySession.timer) {
        clearInterval(studySession.timer);
    }
    
    const sessionDuration = Math.floor((Date.now() - studySession.startTime) / 1000);
    const accuracy = studySession.cardsStudied > 0 ? 
        Math.round((studySession.correctAnswers / studySession.cardsStudied) * 100) : 0;
    
    // Award XP based on performance
    let sessionXP = studySession.cardsStudied * 2;
    if (accuracy >= 80) sessionXP += 10; // Bonus for high accuracy
    if (sessionDuration >= 600) sessionXP += 5; // Bonus for studying 10+ minutes
    
    if (sessionXP > 0) {
        awardXP(sessionXP, 'Study session completed!');
    }
    
    showNotification(
        `Session complete! Studied ${studySession.cardsStudied} cards with ${accuracy}% accuracy. +${sessionXP} XP!`,
        'success'
    );
    
    // Reset session
    studySession = {
        active: false,
        startTime: null,
        currentCard: 0,
        cardsStudied: 0,
        correctAnswers: 0,
        timer: null,
        cards: []
    };
    
    // Reset UI safely
    const elements = {
        startBtn: document.getElementById('start-session-btn'),
        pauseBtn: document.getElementById('pause-session-btn'),
        endBtn: document.getElementById('end-session-btn'),
        reviewInterface: document.getElementById('review-interface'),
        sessionTimer: document.getElementById('session-timer')
    };
    
    if (elements.startBtn) elements.startBtn.classList.remove('hidden');
    if (elements.pauseBtn) elements.pauseBtn.classList.add('hidden');
    if (elements.endBtn) elements.endBtn.classList.add('hidden');
    if (elements.reviewInterface) elements.reviewInterface.classList.add('hidden');
    if (elements.sessionTimer) elements.sessionTimer.textContent = '00:00';
    if (elements.pauseBtn) elements.pauseBtn.innerHTML = '<i class="fas fa-pause"></i> Pause';
}

function updateSessionTimer() {
    const timerElement = document.getElementById('session-timer');
    if (!timerElement || !studySession.active || !studySession.startTime) return;
    
    const elapsed = Math.floor((Date.now() - studySession.startTime) / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    
    timerElement.textContent = 
        `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

function showCurrentCard() {
    if (!studySession.cards || studySession.currentCard >= studySession.cards.length) {
        endStudySession();
        return;
    }
    
    const card = studySession.cards[studySession.currentCard];
    const xpValue = XP_VALUES[card.difficulty] || 5;
    
    const elements = {
        studyQuestion: document.getElementById('study-question'),
        studyAnswer: document.getElementById('study-answer'),
        studyXpBadge: document.getElementById('study-xp-badge'),
        studyXpBadgeBack: document.getElementById('study-xp-badge-back'),
        studyDifficultyBadge: document.getElementById('study-difficulty-badge'),
        studyDifficultyBadgeBack: document.getElementById('study-difficulty-badge-back'),
        studyProgressFill: document.getElementById('study-progress-fill'),
        progressText: document.getElementById('progress-text'),
        studyFlashcard: document.getElementById('study-flashcard'),
        revealBtn: document.getElementById('reveal-answer-btn'),
        answerControls: document.getElementById('answer-controls')
    };
    
    // Update card display safely
    if (elements.studyQuestion) elements.studyQuestion.textContent = card.question;
    if (elements.studyAnswer) elements.studyAnswer.textContent = card.answer;
    
    // Update XP badges
    if (elements.studyXpBadge) elements.studyXpBadge.textContent = `${xpValue} XP`;
    if (elements.studyXpBadgeBack) elements.studyXpBadgeBack.textContent = `${xpValue} XP`;
    
    // Update difficulty badges
    const difficultyText = (card.difficulty || 'medium').charAt(0).toUpperCase() + (card.difficulty || 'medium').slice(1);
    if (elements.studyDifficultyBadge) {
        elements.studyDifficultyBadge.className = `difficulty-badge difficulty-${card.difficulty || 'medium'}`;
        elements.studyDifficultyBadge.textContent = difficultyText;
    }
    if (elements.studyDifficultyBadgeBack) {
        elements.studyDifficultyBadgeBack.className = `difficulty-badge difficulty-${card.difficulty || 'medium'}`;
        elements.studyDifficultyBadgeBack.textContent = difficultyText;
    }
    
    // Update progress
    const progress = ((studySession.currentCard + 1) / studySession.cards.length) * 100;
    if (elements.studyProgressFill) elements.studyProgressFill.style.width = `${progress}%`;
    if (elements.progressText) elements.progressText.textContent = 
        `Card ${studySession.currentCard + 1} of ${studySession.cards.length}`;
    
    // Reset card state
    if (elements.studyFlashcard) elements.studyFlashcard.classList.remove('flipped');
    if (elements.revealBtn) elements.revealBtn.classList.remove('hidden');
    if (elements.answerControls) elements.answerControls.classList.add('hidden');
}

function revealAnswer() {
    const elements = {
        studyFlashcard: document.getElementById('study-flashcard'),
        revealBtn: document.getElementById('reveal-answer-btn'),
        answerControls: document.getElementById('answer-controls')
    };
    
    if (elements.studyFlashcard) elements.studyFlashcard.classList.add('flipped');
    if (elements.revealBtn) elements.revealBtn.classList.add('hidden');
    if (elements.answerControls) elements.answerControls.classList.remove('hidden');
}

function answerCard(isCorrect) {
    studySession.cardsStudied++;
    if (isCorrect) {
        studySession.correctAnswers++;
        const card = studySession.cards[studySession.currentCard];
        const xpValue = XP_VALUES[card.difficulty] || 5;
        awardXP(xpValue, 'Correct answer!');
    }
    
    // Move to next card
    studySession.currentCard++;
    
    if (studySession.currentCard >= studySession.cards.length) {
        // Session complete
        setTimeout(endStudySession, 1000);
    } else {
        setTimeout(showCurrentCard, 500);
    }
}

// =============================
// Gamification Functions - FIXED
// =============================
function awardXP(amount, reason = '') {
    userStats.xp += amount;
    userStats.totalCards = savedCards.length + generatedCards.length;
    
    // Check for level up
    const newLevel = Math.floor(userStats.xp / 100) + 1;
    if (newLevel > userStats.level) {
        userStats.level = newLevel;
        if (currentUser) currentUser.level = newLevel;
        showLevelUp(newLevel);
    }
    
    showXPGain(amount, reason);
    updateUserDashboard();
}

function showXPGain(amount, reason) {
    const xpGain = document.createElement('div');
    xpGain.className = 'xp-animation';
    xpGain.innerHTML = `+${amount} XP<br><small>${reason}</small>`;
    xpGain.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: linear-gradient(135deg, #4CAF50, #8BC34A);
        color: white;
        padding: 15px 25px;
        border-radius: 10px;
        font-weight: bold;
        text-align: center;
        z-index: 1001;
        animation: xpFloat 2s ease-out forwards;
        box-shadow: 0 5px 20px rgba(76, 175, 80, 0.3);
    `;
    
    document.body.appendChild(xpGain);
    
    setTimeout(() => {
        if (xpGain.parentNode) {
            xpGain.parentNode.removeChild(xpGain);
        }
    }, 2000);
}

function showLevelUp(level) {
    const levelUp = document.createElement('div');
    levelUp.className = 'level-up-notification';
    levelUp.innerHTML = `
        <div style="background: linear-gradient(45deg, #ff6b6b, #feca57); color: white; padding: 20px 30px; 
                    border-radius: 15px; font-size: 1.5rem; font-weight: bold; text-align: center;
                    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 1002;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3); animation: levelUp 0.5s ease-out;">
            <i class="fas fa-trophy" style="font-size: 2rem; display: block; margin-bottom: 10px;"></i>
            Level Up!<br>
            <span style="font-size: 1rem;">You reached level ${level}!</span>
        </div>
    `;
    document.body.appendChild(levelUp);
    
    setTimeout(() => {
        if (levelUp.parentNode) {
            levelUp.parentNode.removeChild(levelUp);
        }
    }, 3000);
}

// =============================
// Timetable Functions - FIXED
// =============================
function showTimetableForm() {
    const form = document.getElementById('timetable-form');
    if (form) form.classList.remove('hidden');
}

function hideTimetableForm() {
    const form = document.getElementById('timetable-form');
    if (form) form.classList.add('hidden');
    clearTimetableForm();
}

function clearTimetableForm() {
    const elements = {
        subject: document.getElementById('timetable-subject'),
        day: document.getElementById('timetable-day'),
        start: document.getElementById('timetable-start'),
        end: document.getElementById('timetable-end')
    };
    
    if (elements.subject) elements.subject.value = 'math';
    if (elements.day) elements.day.value = 'Monday';
    if (elements.start) elements.start.value = '';
    if (elements.end) elements.end.value = '';
}

function saveTimetableItem() {
    const elements = {
        subject: document.getElementById('timetable-subject'),
        day: document.getElementById('timetable-day'),
        start: document.getElementById('timetable-start'),
        end: document.getElementById('timetable-end')
    };
    
    if (!elements.subject || !elements.day || !elements.start || !elements.end) {
        showNotification('Form elements not found!', 'error');
        return;
    }
    
    const subject = elements.subject.value;
    const day = elements.day.value;
    const startTime = elements.start.value;
    const endTime = elements.end.value;
    
    if (!startTime || !endTime) {
        showNotification('Please select both start and end times', 'error');
        return;
    }
    
    if (startTime >= endTime) {
        showNotification('End time must be after start time', 'error');
        return;
    }
    
    const newEntry = { 
        id: Date.now(),
        subject, 
        day, 
        startTime, 
        endTime 
    };
    
    timetableItems.push(newEntry);
    showNotification('Study time added successfully!', 'success');
    hideTimetableForm();
    loadTimetable();
}

async function loadTimetable() {
    renderTimetable(timetableItems);
}

function renderTimetable(timetable) {
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    const timetableDisplay = document.getElementById('timetable-display');
    
    if (!timetableDisplay) {
        console.error('Timetable display element not found');
        return;
    }
    
    timetableDisplay.innerHTML = '<div class="timetable-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;"></div>';
    const grid = timetableDisplay.querySelector('.timetable-grid');
    
    if (!grid) return;
    
    days.forEach(day => {
        const dayDiv = document.createElement('div');
        dayDiv.className = 'timetable-day';
        dayDiv.style.cssText = `
            background: white;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            min-height: 150px;
        `;
        
        const dayHeader = document.createElement('div');
        dayHeader.className = 'day-header';
        dayHeader.textContent = day;
        dayHeader.style.cssText = `
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
            font-size: 1.1rem;
        `;
        dayDiv.appendChild(dayHeader);
        
        // Find entries for this day
        const dayEntries = timetable.filter(entry => entry.day === day);
        dayEntries.sort((a, b) => a.startTime.localeCompare(b.startTime));
        
        dayEntries.forEach(entry => {
            const timeSlot = document.createElement('div');
            timeSlot.className = 'time-slot';
            timeSlot.style.cssText = `
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 10px;
                border-radius: 8px;
                margin-bottom: 10px;
            `;
            
            timeSlot.innerHTML = `
                <div style="font-weight: bold; margin-bottom: 5px;">${getSubjectName(entry.subject)}</div>
                <div style="font-size: 0.9rem; opacity: 0.9;">${entry.startTime} - ${entry.endTime}</div>
            `;
            dayDiv.appendChild(timeSlot);
        });
        
        if (dayEntries.length === 0) {
            const emptySlot = document.createElement('div');
            emptySlot.style.cssText = `
                padding: 20px;
                color: #999;
                font-style: italic;
                text-align: center;
            `;
            emptySlot.textContent = 'No study sessions';
            dayDiv.appendChild(emptySlot);
        }
        
        grid.appendChild(dayDiv);
    });
}

// =============================
// Todo Functions - FIXED
// =============================
function showTodoForm() {
    const form = document.getElementById('todo-form');
    if (form) form.classList.remove('hidden');
}

function hideTodoForm() {
    const form = document.getElementById('todo-form');
    if (form) form.classList.add('hidden');
    clearTodoForm();
}

function clearTodoForm() {
    const elements = {
        title: document.getElementById('todo-title'),
        date: document.getElementById('todo-date'),
        description: document.getElementById('todo-description'),
        priority: document.getElementById('todo-priority'),
        subject: document.getElementById('todo-subject')
    };
    
    if (elements.title) elements.title.value = '';
    if (elements.date) elements.date.value = '';
    if (elements.description) elements.description.value = '';
    if (elements.priority) elements.priority.value = 'medium';
    if (elements.subject) elements.subject.value = 'math';
}

function saveTodoItem() {
    const elements = {
        title: document.getElementById('todo-title'),
        date: document.getElementById('todo-date'),
        priority: document.getElementById('todo-priority'),
        subject: document.getElementById('todo-subject'),
        description: document.getElementById('todo-description')
    };
    
    if (!elements.title || !elements.date) {
        showNotification('Form elements not found!', 'error');
        return;
    }
    
    const title = elements.title.value.trim();
    const date = elements.date.value;
    const priority = elements.priority ? elements.priority.value : 'medium';
    const subject = elements.subject ? elements.subject.value : 'math';
    const description = elements.description ? elements.description.value.trim() : '';
    
    if (!title || !date) {
        showNotification('Please fill in title and due date', 'error');
        return;
    }
    
    const todoItem = {
        id: Date.now(),
        title,
        date,
        priority,
        subject,
        description,
        completed: false
    };
    
    todoItems.push(todoItem);
    displayTodos();
    hideTodoForm();
    showNotification('Todo item added!', 'success');
}

function displayTodos() {
    const container = document.getElementById('todo-list');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (todoItems.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #666; padding: 20px;">No todo items yet. Click "Add Todo" to create one!</p>';
        return;
    }
    
    todoItems.forEach(todo => {
        const todoElement = document.createElement('div');
        todoElement.className = 'todo-item';
        todoElement.style.cssText = `
            background: white;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            gap: 15px;
        `;
        
        const priorityColor = {
            low: '#28a745',
            medium: '#ffc107', 
            high: '#dc3545'
        };
        
        todoElement.innerHTML = `
            <div>
                <input type="checkbox" ${todo.completed ? 'checked' : ''} 
                       onchange="toggleTodo(${todo.id})" 
                       style="transform: scale(1.2);">
            </div>
            <div style="flex: 1;">
                <div style="font-weight: bold; margin-bottom: 5px; ${todo.completed ? 'text-decoration: line-through; opacity: 0.6;' : ''}">${todo.title}</div>
                <div style="font-size: 0.9rem; color: #666;">
                    <span>Due: ${new Date(todo.date).toLocaleDateString()}</span> • 
                    <span style="color: ${priorityColor[todo.priority]}; font-weight: 500;">${todo.priority.toUpperCase()} Priority</span> • 
                    <span>${getSubjectName(todo.subject)}</span>
                </div>
                ${todo.description ? `<div style="margin-top: 8px; font-size: 0.9rem; color: #777;">${todo.description}</div>` : ''}
            </div>
            <div>
                <button onclick="deleteTodo(${todo.id})" 
                        style="background: #dc3545; color: white; border: none; padding: 8px 12px; border-radius: 5px; cursor: pointer;">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        container.appendChild(todoElement);
    });
}

function toggleTodo(id) {
    const todo = todoItems.find(t => t.id === id);
    if (todo) {
        todo.completed = !todo.completed;
        displayTodos();
        
        if (todo.completed) {
            awardXP(2, 'Task completed!');
        }
    }
}

function deleteTodo(id) {
    todoItems = todoItems.filter(t => t.id !== id);
    displayTodos();
    showNotification('Todo deleted!', 'info');
}

// =============================
// Groups Functions - FIXED
// =============================
function loadGroups() {
    const groupsList = document.getElementById('groups-list');
    if (!groupsList) return;
    
    // Create groups from saved cards
    const groups = {};
    savedCards.forEach(card => {
        const groupName = card.group || `${getSubjectName(card.subject)} Cards`;
        if (!groups[groupName]) {
            groups[groupName] = [];
        }
        groups[groupName].push(card);
    });
    
    groupsList.innerHTML = '';
    
    if (Object.keys(groups).length === 0) {
        groupsList.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">No flashcard groups yet. Create and save some flashcards to get started!</div>';
        return;
    }
    
    Object.entries(groups).forEach(([groupName, cards]) => {
        const groupCard = document.createElement('div');
        groupCard.className = 'group-card';
        groupCard.style.cssText = `
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        `;
        
        const progress = Math.floor(Math.random() * 100); // Mock progress
        
        groupCard.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div>
                    <h3 style="margin: 0; color: #333; font-size: 1.2rem;">${groupName}</h3>
                    <p style="margin: 5px 0 0 0; color: #666;">${cards.length} cards • Last studied: 2 days ago</p>
                </div>
                <button onclick="studyGroup('${groupName}')" 
                        style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; 
                               padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: 500;">
                    <i class="fas fa-play"></i> Study
                </button>
            </div>
            <div style="background: #f8f9fa; border-radius: 8px; height: 8px; margin-bottom: 10px;">
                <div style="background: linear-gradient(90deg, #4CAF50, #8BC34A); height: 100%; 
                           border-radius: 8px; width: ${progress}%; transition: width 0.3s ease;"></div>
            </div>
            <div style="font-size: 0.9rem; color: #666;">${progress}% mastered</div>
        `;
        
        groupsList.appendChild(groupCard);
    });
}

function studyGroup(groupName) {
    showNotification(`Starting study session for: ${groupName}`, 'info');
    switchSection('study');
    setTimeout(startStudySession, 500);
}

// =============================
// Progress Functions - FIXED
// =============================
function loadProgressStats() {
    const progressStats = document.getElementById('progress-stats');
    if (!progressStats) return;
    
    // Calculate stats
    const totalStudyTime = Math.floor(Math.random() * 50) + 10;
    const cardsStudied = savedCards.length + (studySession.cardsStudied || 0);
    const averageAccuracy = Math.floor(Math.random() * 30) + 70;
    const streakRecord = userStats.streak || 1;
    
    const subjectBreakdown = {};
    savedCards.forEach(card => {
        if (!subjectBreakdown[card.subject]) {
            subjectBreakdown[card.subject] = 0;
        }
        subjectBreakdown[card.subject]++;
    });
    
    progressStats.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px;">
            <div class="stat-card" style="background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <i class="fas fa-clock" style="font-size: 2rem; color: #6a11cb; margin-bottom: 10px;"></i>
                <div style="font-size: 1.5rem; font-weight: bold; color: #333;">${totalStudyTime}h 34m</div>
                <div style="color: #666;">Total Study Time</div>
            </div>
            <div class="stat-card" style="background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <i class="fas fa-brain" style="font-size: 2rem; color: #2575fc; margin-bottom: 10px;"></i>
                <div style="font-size: 1.5rem; font-weight: bold; color: #333;">${cardsStudied}</div>
                <div style="color: #666;">Cards Studied</div>
            </div>
            <div class="stat-card" style="background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <i class="fas fa-bullseye" style="font-size: 2rem; color: #28a745; margin-bottom: 10px;"></i>
                <div style="font-size: 1.5rem; font-weight: bold; color: #333;">${averageAccuracy}%</div>
                <div style="color: #666;">Average Accuracy</div>
            </div>
            <div class="stat-card" style="background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <i class="fas fa-fire" style="font-size: 2rem; color: #ff6b6b; margin-bottom: 10px;"></i>
                <div style="font-size: 1.5rem; font-weight: bold; color: #333;">${streakRecord}</div>
                <div style="color: #666;">Best Streak</div>
            </div>
        </div>
        
        <div style="background: white; border-radius: 10px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <h3 style="margin-bottom: 20px; color: #333;">Subject Progress</h3>
            ${Object.entries(subjectBreakdown).map(([subject, count]) => `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <span style="font-weight: 500; color: #333; min-width: 100px;">${getSubjectName(subject)}</span>
                    <div style="flex: 1; margin: 0 15px;">
                        <div style="background: #e9ecef; border-radius: 10px; height: 8px; overflow: hidden;">
                            <div style="background: linear-gradient(90deg, #4CAF50, #8BC34A); height: 100%; 
                                       width: ${Math.min(100, (count / Math.max(cardsStudied, 1)) * 100)}%; 
                                       transition: width 0.3s ease; border-radius: 10px;"></div>
                        </div>
                    </div>
                    <span style="font-weight: bold; color: #666; min-width: 60px; text-align: right;">${count} cards</span>
                </div>
            `).join('')}
        </div>
    `;
}

// =============================
// Notification Functions - FIXED
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
// Utility Functions
// =============================
function getSubjectName(subjectCode) {
    const subjects = {
        math: 'Mathematics',
        english: 'English',
        spanish: 'Spanish',
        german: 'German',
        science: 'Science',
        history: 'History',
        other: 'Other'
    };
    return subjects[subjectCode] || subjectCode.charAt(0).toUpperCase() + subjectCode.slice(1);
}

// =============================
// Event Listeners Setup - FIXED
// =============================
function setupEventListeners() {
    // Navigation tabs - with safe event handling
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.preventDefault();
            const section = e.target.dataset.section || e.target.closest('[data-section]')?.dataset.section;
            if (section) {
                switchSection(section);
            }
        });
    });

    // Logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            handleLogout();
        });
    }

    // Flashcard creation
    const generateBtn = document.getElementById('generate-ai-btn');
    if (generateBtn) {
        generateBtn.addEventListener('click', generateAIFlashcards);
    }

    const addManualBtn = document.getElementById('add-manual-btn');
    if (addManualBtn) {
        addManualBtn.addEventListener('click', addManualCard);
    }

    const saveCardsBtn = document.getElementById('save-cards-btn');
    if (saveCardsBtn) {
        saveCardsBtn.addEventListener('click', saveAllCards);
    }

    const clearAllBtn = document.getElementById('clear-all-btn');
    if (clearAllBtn) {
        clearAllBtn.addEventListener('click', clearAllCards);
    }
    
    // Preview updates
    const difficultySelect = document.getElementById('difficulty-select');
    if (difficultySelect) {
        difficultySelect.addEventListener('change', updatePreviewCard);
    }

    const manualQuestion = document.getElementById('manual-question');
    if (manualQuestion) {
        manualQuestion.addEventListener('input', updatePreviewCard);
    }

    const manualAnswer = document.getElementById('manual-answer');
    if (manualAnswer) {
        manualAnswer.addEventListener('input', updatePreviewCard);
    }
    
    // Preview card flip
    const previewFlashcard = document.getElementById('preview-flashcard');
    if (previewFlashcard) {
        previewFlashcard.addEventListener('click', function() {
            this.classList.toggle('flipped');
        });
    }

    // Study session
    const startSessionBtn = document.getElementById('start-session-btn');
    if (startSessionBtn) {
        startSessionBtn.addEventListener('click', startStudySession);
    }

    const pauseSessionBtn = document.getElementById('pause-session-btn');
    if (pauseSessionBtn) {
        pauseSessionBtn.addEventListener('click', pauseStudySession);
    }

    const endSessionBtn = document.getElementById('end-session-btn');
    if (endSessionBtn) {
        endSessionBtn.addEventListener('click', endStudySession);
    }

    const revealAnswerBtn = document.getElementById('reveal-answer-btn');
    if (revealAnswerBtn) {
        revealAnswerBtn.addEventListener('click', revealAnswer);
    }

    const correctBtn = document.getElementById('correct-btn');
    if (correctBtn) {
        correctBtn.addEventListener('click', () => answerCard(true));
    }

    const incorrectBtn = document.getElementById('incorrect-btn');
    if (incorrectBtn) {
        incorrectBtn.addEventListener('click', () => answerCard(false));
    }

    // Timetable
    const addTimetableBtn = document.getElementById('add-timetable-btn');
    if (addTimetableBtn) {
        addTimetableBtn.addEventListener('click', showTimetableForm);
    }

    const saveTimetableBtn = document.getElementById('save-timetable-btn');
    if (saveTimetableBtn) {
        saveTimetableBtn.addEventListener('click', saveTimetableItem);
    }

    const cancelTimetableBtn = document.getElementById('cancel-timetable-btn');
    if (cancelTimetableBtn) {
        cancelTimetableBtn.addEventListener('click', hideTimetableForm);
    }
    
    // Todo
    const addTodoBtn = document.getElementById('add-todo-btn');
    if (addTodoBtn) {
        addTodoBtn.addEventListener('click', showTodoForm);
    }

    const saveTodoBtn = document.getElementById('save-todo-btn');
    if (saveTodoBtn) {
        saveTodoBtn.addEventListener('click', saveTodoItem);
    }

    const cancelTodoBtn = document.getElementById('cancel-todo-btn');
    if (cancelTodoBtn) {
        cancelTodoBtn.addEventListener('click', hideTodoForm);
    }
}

// =============================
// Initialize Application - FIXED
// =============================
async function initializeApp() {
    console.log('Initializing AI Study Buddy...');
    
    try {
        // Check authentication and setup demo user
        checkAuthStatus();
        
        // Test backend connection (optional)
        backendConnected = await testBackendConnection();
        
        // Setup event listeners with error handling
        setupEventListeners();
        
        // Initialize UI state
        updateUIForAuthState();
        updateUserDashboard();
        updatePreviewCard();
        
        // Initialize displays
        displayTodos();
        loadTimetable();
        
        // Start with home section
        switchSection('home');
        
        console.log('AI Study Buddy initialized successfully!');
        showNotification('Welcome to AI Study Buddy!', 'success');
        
    } catch (error) {
        console.error('Initialization error:', error);
        showNotification('App initialized with limited features', 'warning');
    }
}



// Add this test function to main.js
async function testHuggingFace() {
    try {
        const response = await makeAPICall('/test_huggingface', {
            method: 'POST',
            body: JSON.stringify({
                notes: document.getElementById('notes-input').value || 'Test notes about science'
            })
        });
        
        console.log('HuggingFace Test Result:', response);
        showNotification('Check console for HuggingFace test results', 'info');
    } catch (error) {
        console.error('HuggingFace test failed:', error);
        showNotification(`HuggingFace test failed: ${error.message}`, 'error');
    }
}
// Add this function to main.js
async function testHuggingFaceConnection() {
    const testBtn = document.getElementById('test-huggingface-btn');
    const originalText = testBtn.innerHTML;
    testBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    testBtn.disabled = true;
    
    try {
        const testNotes = document.getElementById('notes-input').value || 
                         'Artificial intelligence is transforming how we solve complex problems.';
        
        const response = await makeAPICall('/test_huggingface', {
            method: 'POST',
            body: JSON.stringify({
                notes: testNotes,
                subject: document.getElementById('subject-select').value,
                difficulty: document.getElementById('difficulty-select').value
            })
        });
        
        console.log('HuggingFace Test Results:', response);
        
        if (response.token_configured) {
            showNotification('HuggingFace API connected successfully!', 'success');
            console.log('API Status:', response.api_status);
            console.log('Test Generation:', response.test_generation);
        } else {
            showNotification('HuggingFace token not configured', 'error');
        }
        
    } catch (error) {
        console.error('HuggingFace test error:', error);
        showNotification(`Test failed: ${error.message}`, 'error');
    } finally {
        testBtn.innerHTML = originalText;
        testBtn.disabled = false;
    }
}

// Add event listener in your setupEventListeners function
document.getElementById('test-huggingface-btn').addEventListener('click', testHuggingFaceConnection);


// =============================
// Authentication Functions
// =============================
function checkAuthStatus() {
    const token = localStorage.getItem('ai_study_buddy_token');
    const userData = localStorage.getItem('ai_study_buddy_user');
    
    if (!token || !userData) {
        window.location.href = 'login.html';
        return false;
    }
    
    try {
        currentUser = JSON.parse(userData);
        authToken = token;
        
        userStats = {
            level: currentUser.level,
            xp: currentUser.xp,
            streak: currentUser.streak,
            totalCards: savedCards.length + generatedCards.length
        };
        
        return true;
    } catch (error) {
        console.error('Error parsing user data:', error);
        localStorage.removeItem('ai_study_buddy_token');
        localStorage.removeItem('ai_study_buddy_user');
        window.location.href = 'login.html';
        return false;
    }
}

function handleLogout() {
    // Clear stored data
    localStorage.removeItem('ai_study_buddy_token');
    localStorage.removeItem('ai_study_buddy_user');
    
    // Reset application state
    authToken = null;
    currentUser = null;
    currentCards = [];
    generatedCards = [];
    savedCards = [];
    
    // Reset user stats
    userStats = {
        level: 1,
        xp: 0,
        streak: 0,
        totalCards: 0
    };
    
    showNotification('Logged out successfully', 'info');
    
    // Redirect to login page
    setTimeout(() => {
        window.location.href = 'login.html';
    }, 1000);
}

function updateUIForAuthState() {
    if (!currentUser) return;
    
    // Update user displays
    document.getElementById('username-display').textContent = currentUser.username;
    document.getElementById('user-plan-nav').textContent = currentUser.plan;
    
    // Show all authenticated elements
    document.getElementById('user-dashboard').classList.remove('hidden');
    document.getElementById('level-progress-container').classList.remove('hidden');
    document.getElementById('logout-btn').classList.remove('hidden');
    document.getElementById('user-welcome').classList.remove('hidden');
    
    // Show app navigation tabs
    const appTabs = document.querySelectorAll('[data-section="create"], [data-section="study"], [data-section="groups"], [data-section="progress"], [data-section="timetable"]');
    appTabs.forEach(tab => tab.classList.remove('hidden'));
}
// Add this button to your HTML for testing
// <button onclick="testHuggingFace()">Test HuggingFace</button>
// =============================
// App Entry Point
// =============================
document.addEventListener('DOMContentLoaded', initializeApp);