# vibe_code
hackethon
# 📘 AI Study Buddy – Project Prompt & Requirements

## 🎯 Goal

Build a full-stack **AI Study Buddy web app** that helps learners study smarter.
It combines **AI-powered flashcard generation**, **gamification** (XP, streaks), and **study planning** (timetable, reminders, notifications).

---

## ✅ Core Requirements

### 1. **User Accounts & Authentication**

* User registration & login (name, email, password).
* Store users in database.
* Each user has:

  * **Daily streak count**
  * **XP points**
  * **Last visit date**
  * **Personal timetable**
  * **Reminders & notifications**

---

### 2. **Gamification**

* **Daily Streaks**: Track login streaks (reset if missed a day).
* **XP Points**: Earn XP for actions (flipping flashcards, adding tasks, completing reminders).
* **Levels (future)**: XP translates into progress levels.

---

### 3. **Study Planner**

* **Timetable (weekly)**: Add subjects per day/time.
* **Reminders**: Users can set reminders with datetime.
* **Notifications**: Show upcoming reminders and study alerts in dashboard.

---

### 4. **Flashcard Generator**

* Input: user pastes notes.
* Output: generates **Q\&A flashcards** (frontend demo done).
* Later: call **Hugging Face API** in backend for real AI flashcards.

---

### 5. **Dashboard**

* Shows:

  * Daily streak
  * XP points
  * Last visit date
  * Timetable
  * Notifications & reminders
  * Flashcard generator
  * **Recommended resources based on last subject studied**

---

### 6. **Frontend (HTML/CSS/JS)**

* `index.html` → app layout & dashboard.
* `static/style.css` → UI design (cards, panels, grid, responsive).
* `static/app.js` → handles login, register, API calls, dashboard rendering.

---

### 7. **Backend (Python / Flask)**

* `app.py` → Flask app with endpoints:

  * `/api/register` → register user
  * `/api/login` → login user
  * `/api/dashboard` → return streak, XP, timetable, notifications, last visit
  * `/api/timetable/add` → add timetable row
  * `/api/reminder/add` → add reminder
  * `/api/xp/add` → add XP
  * `/api/notifications` → fetch notifications
* Uses **Flask + SQLAlchemy** with **SQLite or MySQL**.

---

### 8. **Database (SQLAlchemy models)**

* **User**

  * id, name, email, password, token
  * xp, streak, last\_visit
* **TimetableItem**

  * user\_id, day, time, subject
* **Reminder**

  * user\_id, text, datetime
* **Notification**

  * user\_id, title, body, dt

---

## 📋 Plans (Next Steps)

### Phase 1 (Done ✅)

* [x] Core CRUD API endpoints
* [x] User registration + login
* [x] Timetable add & view

* [x] XP system + streak updates
* [x] Frontend UI with dashboard

---

### Phase 2 (🔜 Next)

* [ ] **Secure passwords** with hashing (bcrypt).
* [ ] **Switch to JWT auth** instead of plain tokens.
* [ ] **Reminder notifications** (email/push/cron with APScheduler).
* [ ] **XP levels & achievements** (badges, ranks).
* [ ] **Delete / edit timetable & reminders** (CRUD).
* [x] Reminders + notifications

---

### Phase 3 (🚀 Future Features)

* [ ] **Hugging Face API integration** for AI flashcards.
* [ ] **Recommended resources engine** (ML or rules-based).
* [ ] **Leaderboard / community challenges**.
* [ ] **Mobile-friendly PWA** (push notifications).

---

## 📦 Tech Stack

* **Frontend**: HTML, CSS, JavaScript (vanilla, modular).
* **Backend**: Python (Flask, SQLAlchemy).
* **Database**: SQLite (dev) → MySQL (prod).
* **Deployment**: Hugging Face Spaces / Render / Heroku.
