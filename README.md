# Antlers

A web application for lending, borrowing, donating, and returning items, built with Flask.

## Features
- User registration, login, and email verification
- Lend, borrow, donate, and return items
- Admin dashboard for approvals
- Chat and notification system (via Gmail)
- Track donations, returns, and swaps

## Setup

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd Antlers
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Set environment variables:**
   - `GMAIL_USER`: Gmail address for sending notifications
   - `GMAIL_PASS`: Gmail app password
   - (Optional) Other Flask config variables as needed

   You can use a `.env` file (not tracked by git):
   ```
   GMAIL_USER=your-email@gmail.com
   GMAIL_PASS=your-app-password
   ```

4. **Initialize the database:**

   ```bash
   python init_db.py
   ```

5. **Run the app:**
   ```bash
   python app.py
   ```

## Usage
- Access the app at `http://127.0.0.1:5000/`
- Register, verify your email, and start lending, borrowing, or donating items!
- Admins can approve/reject items and manage users.

## Notes
- Uploaded files and the SQLite database are not tracked by git.
- For production, configure environment variables securely and use a production-ready server.

---

**Made with ❤️ using Flask.** 

@app.route('/secret')
@login_required
def secret():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    
    users = User.query.all()
    return render_template('secret.html' , navi=users)    return render_template('secret.html' , navi=users)
