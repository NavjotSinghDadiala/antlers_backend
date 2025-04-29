from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from os import environ


app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'  # Use forward slash instead of os.path.join
app.config['SQLALCHEMY_DATABASE_URI'] = environ.get('DATABASE_URL') or 'sqlite:///antlers.db'
app.config['SECRET_KEY'] = environ.get('SECRET_KEY') or 'secretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'  

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app) 
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Import models after db initialization
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True)
    contact_number = db.Column(db.String(20))
    role = db.Column(db.String(50), default='user')
    created_at = db.Column(db.DateTime, default=func.now())
    
    # Relationships
    approved_items = db.relationship('Accessory', 
                                   foreign_keys='Accessory.user_id',
                                   backref=db.backref('owner', lazy=True))
    
    # Borrowed items (items this user has borrowed)
    items_borrowed = db.relationship('BorrowedAccessory',
                                   foreign_keys='BorrowedAccessory.borrower_id',
                                   backref=db.backref('borrower_user', lazy=True))
    
    # Lent items (items this user has lent to others)
    items_lent = db.relationship('BorrowedAccessory',
                                foreign_keys='BorrowedAccessory.lender_id',
                                backref=db.backref('lender_user', lazy=True))

class PendingAccessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    description = db.Column(db.String(500))
    category = db.Column(db.String(50))
    location = db.Column(db.String(150))
    image = db.Column(db.String(150))
    type = db.Column(db.String(50))  # 'lend' or 'donate'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    datetime = db.Column(db.DateTime, default=func.now())
    contact_shared = db.Column(db.Boolean, default=False)
    residence = db.Column(db.String(200))  # User's residence
    
    # Relationship with User
    user = db.relationship('User', backref='pending_items')

class Accessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    description = db.Column(db.String(500))
    category = db.Column(db.String(50))
    location = db.Column(db.String(150))
    image = db.Column(db.String(150))
    is_available = db.Column(db.Boolean, default=True)
    type = db.Column(db.String(50))  # 'lend' or 'donate'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=func.now())

class BorrowedAccessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    accessory_id = db.Column(db.Integer, db.ForeignKey('accessory.id'))
    borrower_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    lender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(50))  # 'pending', 'approved', 'rejected', 'delivered', 'returned'
    pickup_location = db.Column(db.String(150))
    pickup_datetime = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=func.now())
    residence = db.Column(db.String(200), nullable=False)  # Borrower's residence
    message = db.Column(db.Text, nullable=False)  # Message to lender
    delivery_preference = db.Column(db.String(50), default='self')  # 'self' or 'antlers'
    lender_confirmed_delivery = db.Column(db.Boolean, default=False)
    borrower_confirmed_delivery = db.Column(db.Boolean, default=False)
    
    # Relationships
    accessory = db.relationship('Accessory', backref='borrow_requests')
    borrower = db.relationship('User', foreign_keys=[borrower_id], backref='items_borrowed_as_borrower')
    lender = db.relationship('User', foreign_keys=[lender_id], backref='items_lent_as_lender')

class RejectedBorrowRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    accessory_id = db.Column(db.Integer, db.ForeignKey('accessory.id'))
    borrower_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    lender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    pickup_location = db.Column(db.String(150))
    pickup_datetime = db.Column(db.DateTime)
    residence = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)  # Original message from borrower
    rejection_reason = db.Column(db.Text, nullable=False)  # Reason for rejection
    created_at = db.Column(db.DateTime)  # When the original request was created
    rejected_at = db.Column(db.DateTime, default=func.now())  # When it was rejected
    delivery_preference = db.Column(db.String(50), default='self')  # 'self' or 'antlers'
    
    # Relationships
    accessory = db.relationship('Accessory', backref='rejected_borrow_requests')
    borrower = db.relationship('User', foreign_keys=[borrower_id], backref='rejected_requests_as_borrower')
    lender = db.relationship('User', foreign_keys=[lender_id], backref='rejected_requests_as_lender')

class ReturnedAccessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    accessory_id = db.Column(db.Integer, db.ForeignKey('accessory.id'))
    borrower_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    lender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(50), default='pending')  # pending, approved, completed
    created_at = db.Column(db.DateTime, default=func.now())
    return_location = db.Column(db.String(150))
    pickup_location = db.Column(db.String(150))
    return_datetime = db.Column(db.String(100))
    return_notes = db.Column(db.String(200))
    item_name = db.Column(db.String(100))
    lender_confirmed_return = db.Column(db.Boolean, default=False)
    borrower_confirmed_return = db.Column(db.Boolean, default=False)
    rejection_reason = db.Column(db.Text)
    
    # Add relationships
    accessory = db.relationship('Accessory', backref='return_requests')
    borrower = db.relationship('User', foreign_keys=[borrower_id], backref='returned_items')
    lender = db.relationship('User', foreign_keys=[lender_id], backref='received_returns')

class BorrowHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100))
    item_category = db.Column(db.String(100))
    borrower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    borrow_date = db.Column(db.DateTime, default=func.now())
    return_date = db.Column(db.DateTime)
    pickup_location = db.Column(db.String(150))
    return_location = db.Column(db.String(150))
    
    # Add relationships
    borrower = db.relationship('User', foreign_keys=[borrower_id], backref='borrow_history')
    lender = db.relationship('User', foreign_keys=[lender_id], backref='lend_history')

class RejectedAccessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    image = db.Column(db.String(255))
    location = db.Column(db.String(100), nullable=False)
    residence = db.Column(db.String(200), nullable=False)
    datetime = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text)
    type = db.Column(db.String(20), nullable=False)  # 'lend' or 'donate'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rejected_at = db.Column(db.DateTime, default=func.now())
    rejection_reason = db.Column(db.Text, nullable=False)
    
    user = db.relationship('User', backref=db.backref('rejected_items', lazy=True))

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    borrow_id = db.Column(db.Integer, db.ForeignKey('borrowed_accessory.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=func.now())
    is_read = db.Column(db.Boolean, default=False)

    # Relationships
    borrow_request = db.relationship('BorrowedAccessory', backref=db.backref('chat_messages', lazy=True, order_by='ChatMessage.timestamp'))
    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_messages', lazy=True))
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref=db.backref('received_messages', lazy=True))

# Function to create tables and the admin user
def create_tables_and_admin():
    db.create_all()  # Creates tables if they don't exist
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='antlers@admin2003', role='admin')
        db.session.add(admin)
        db.session.commit()

def recreate_database():
    """Drop all tables and recreate them with the new schema"""
    db.drop_all()
    db.create_all()
    # Recreate admin user
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='antlers@admin2003', role='admin')
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def main():
    return render_template('main.html')

@app.route('/home')
def home():
    # Only show items that are available
    items = Accessory.query.filter_by(is_available=True).all()
    return render_template('home.html', items=items)

@app.route('/what-we-offer')
def what_we_offer():
    """Render the 'What We Offer' page"""
    return render_template('what_we_offer.html')

@app.route('/how-it-works')
def how_it_works():
    """Render the 'How It Works' page"""
    return render_template('how_it_works.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        email = request.form['email']
        contact_number = request.form['contact_number']
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
            
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
            
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))
            
        # Check password length
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return redirect(url_for('register'))
            
        user = User(
            username=username, 
            password=password,
            email=email,
            contact_number=contact_number,
            role='user'
        )
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/user')
@login_required
def user_dashboard():
    # Get user's own items (both approved and pending)
    my_approved_items = Accessory.query.filter_by(user_id=current_user.id).all()
    my_pending_items = PendingAccessory.query.filter_by(user_id=current_user.id).all()
    
    # Get rejected items for the current user
    rejected_items = RejectedAccessory.query.filter_by(user_id=current_user.id).order_by(RejectedAccessory.rejected_at.desc()).all()
    
    # Get items borrowed by the user with their relationships
    borrowed_items = BorrowedAccessory.query.filter_by(borrower_id=current_user.id).options(
        db.joinedload(BorrowedAccessory.lender_user),
        db.joinedload(BorrowedAccessory.accessory)
    ).all()
    
    # Get borrow requests for items owned by the user
    borrow_requests = BorrowedAccessory.query.join(Accessory).filter(
        Accessory.user_id == current_user.id,
        BorrowedAccessory.status == 'pending'
    ).all()
    
    # Get rejected borrow requests where the user was the borrower
    rejected_borrow_requests = RejectedBorrowRequest.query.filter_by(
        borrower_id=current_user.id
    ).order_by(RejectedBorrowRequest.rejected_at.desc()).all()
    
    # Get rejected return requests where the user was the borrower
    rejected_return_requests = ReturnedAccessory.query.filter(
        ReturnedAccessory.borrower_id == current_user.id,
        ReturnedAccessory.status == 'rejected'
    ).options(
        db.joinedload(ReturnedAccessory.lender),
        db.joinedload(ReturnedAccessory.accessory)
    ).order_by(ReturnedAccessory.created_at.desc()).all()
    
    # Initialize shown rejection notifications in session if not present
    if 'shown_rejection_notifications' not in session:
        session['shown_rejection_notifications'] = []
    
    # Check for rejected return requests and show notification only once
    three_days_ago = datetime.now() - timedelta(days=3)
    for rejected_return in rejected_return_requests:
        # Only show recent rejections (within last 3 days) that haven't been shown before
        if (rejected_return.created_at and 
            rejected_return.created_at > three_days_ago and 
            str(rejected_return.id) not in session['shown_rejection_notifications']):
            flash(f'Your return request for {rejected_return.item_name} was rejected. Reason: {rejected_return.rejection_reason}', 'warning')
            # Mark this notification as shown
            session['shown_rejection_notifications'].append(str(rejected_return.id))
            session.modified = True
    
    return render_template('user_dashboard.html', 
                         my_approved_items=my_approved_items,
                         my_pending_items=my_pending_items,
                         borrowed_items=borrowed_items,
                         borrow_requests=borrow_requests,
                         rejected_items=rejected_items,
                         rejected_borrow_requests=rejected_borrow_requests,
                         rejected_return_requests=rejected_return_requests)

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    
    # Get all data for admin dashboard
    users = User.query.all()
    pending_items = PendingAccessory.query.all()
    approved_items = Accessory.query.all()
    borrowed_items = BorrowedAccessory.query.all()
    return_requests = ReturnedAccessory.query.all()
    borrow_history = BorrowHistory.query.all()
    
    # Calculate statistics
    stats = {
        'total_users': len([u for u in users if u.role != 'admin']),
        'pending_items': len(pending_items),
        'approved_items': len(approved_items),
        'active_borrows': len([b for b in borrowed_items if b.status == 'approved'])
    }
    
    return render_template('admin_dashboard.html',
                         users=users,
                         items=pending_items,
                         approved_items=approved_items,
                         borrowed_items=borrowed_items,
                         return_requests=return_requests,
                         borrow_history=borrow_history,
                         stats=stats)

@app.route('/approve/<int:item_id>')
@login_required
def approve(item_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    pending_item = PendingAccessory.query.get_or_404(item_id)
    
    # Create new accessory
    accessory = Accessory(
        name=pending_item.name,
        description=pending_item.description,
        image=pending_item.image,
        type=pending_item.type,
        category=pending_item.category,
        location=pending_item.location,
        user_id=pending_item.user_id,
        is_available=True
    )
    
    # Add to accessories and delete from pending
    db.session.add(accessory)
    db.session.delete(pending_item)
    db.session.commit()
    
    flash('Item approved successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/reject/<int:item_id>', methods=['GET', 'POST'])
@login_required
def reject(item_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('home'))
        
    pending_item = PendingAccessory.query.get_or_404(item_id)
    
    if request.method == 'POST':
        rejection_reason = request.form.get('rejection_reason', '').strip()
        if not rejection_reason:
            flash('Please provide a reason for rejection', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        # Create rejected accessory entry
        rejected_item = RejectedAccessory(
            name=pending_item.name,
            category=pending_item.category,
            image=pending_item.image,
            location=pending_item.location,
            residence=pending_item.residence,
            datetime=pending_item.datetime,
            description=pending_item.description,
            type=pending_item.type,
            user_id=pending_item.user_id,
            rejection_reason=rejection_reason
        )
        
        try:
            db.session.add(rejected_item)
            db.session.delete(pending_item)
            db.session.commit()
            flash('Item has been rejected ... User will be notified.', 'warning')
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while rejecting the item.', 'danger')
            
        return redirect(url_for('admin_dashboard'))
    
    return render_template('reject_item.html', item=pending_item)

def save_file(file):
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        return f'uploads/{filename}'  # Return relative path for template
    return None

@app.route('/borrow')
@login_required
def borrow():
    # Get items that are available and not owned by the current user
    available_items = Accessory.query.filter(
        Accessory.is_available == True,
        Accessory.user_id != current_user.id
    ).all()
    return render_template('borrow.html', items=available_items)

@app.route('/lend', methods=['GET', 'POST'])
@login_required
def lend():
    if request.method == 'POST':
        try:
            # Convert datetime string to Python datetime object
            datetime_str = request.form['datetime']
            pickup_datetime = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M')
            
            # Handle image upload
            file = request.files.get('image')
            image_path = None
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                image_path = os.path.join('uploads', filename)
            
            # Create pending item
            pending_item = PendingAccessory(
                name=request.form['name'],
                description=request.form.get('description'),
                category=request.form['category'],
                location=request.form['location'],
                residence=request.form['residence'],
                datetime=pickup_datetime,
                image=image_path,
                type='lend',
                contact_shared=bool(request.form.get('contact_shared')),
                user_id=current_user.id
            )
            
            db.session.add(pending_item)
            db.session.commit()
            flash('Item submitted for approval!', 'success')
            return redirect(url_for('user_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error in lend route: {str(e)}")  # For debugging
            flash('An error occurred while submitting your item.', 'error')
            return redirect(url_for('lend'))
            
    return render_template('lend.html')

@app.route('/donate', methods=['GET', 'POST'])
@login_required
def donate():
    if request.method == 'POST':
        image = save_file(request.files.get('image'))
        pending_item = PendingAccessory(
            name=request.form['name'],
            image=image,
            type='donate',
            category=request.form['category'],
            location=request.form['location'],
            datetime=request.form['datetime'],
            contact_shared=bool(request.form.get('contact_shared')),
            user_id=current_user.id
        )
        db.session.add(pending_item)
        db.session.commit()
        flash('Donation request submitted for approval', 'success')
        return redirect(url_for('user_dashboard'))
    return render_template('donate.html')

@app.route('/borrow_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def borrow_item(item_id):
    item = Accessory.query.get_or_404(item_id)
    if request.method == 'POST':
        if not request.form.get('pickup_location') or not request.form.get('pickup_datetime') or not request.form.get('residence') or not request.form.get('message') or not request.form.get('terms_agreement'):
            flash('Please fill in all required fields and agree to the terms', 'error')
            return redirect(url_for('borrow_item', item_id=item_id))
            
        # Convert datetime string to Python datetime object
        pickup_datetime = datetime.strptime(request.form['pickup_datetime'], '%Y-%m-%dT%H:%M')
            
        # Create a new borrowed accessory record
        borrowed_item = BorrowedAccessory(
            accessory_id=item.id,
            borrower_id=current_user.id,
            lender_id=item.user_id,
            pickup_location=request.form['pickup_location'],
            pickup_datetime=pickup_datetime,
            status='pending',
            residence=request.form['residence'],
            message=request.form.get('message', ''),  # Optional message
            delivery_preference=request.form.get('delivery_preference', 'self')
        )
        db.session.add(borrowed_item)
        db.session.commit()
        flash('Borrow request submitted successfully', 'success')
        return redirect(url_for('user_dashboard'))
    
    # Create a wrapper object that mimics a BorrowedAccessory for the template
    class BorrowRequestWrapper:
        def __init__(self, item):
            self.accessory = item
            self.status = 'new_request'  # Indicate this is a new request
            self.id = None
            self.created_at = datetime.now()
            self.pickup_location = None
            self.pickup_datetime = None
            self.lender_user = item.owner if hasattr(item, 'owner') else None
            self.borrower_user = current_user
            self.residence = None
            self.message = None
            self.lender_confirmed_delivery = False
            self.borrower_confirmed_delivery = False
            self.lender_id = item.user_id
            self.borrower_id = current_user.id
    
    # Wrap the item in an object with the structure the template expects
    borrow_request = BorrowRequestWrapper(item)
    
    return render_template('borrow_details.html', borrow_request=borrow_request, item=item)

@app.route('/borrow_requests')
@login_required
def borrow_requests():
    # Get pending requests for items owned by the user
    pending_requests = BorrowedAccessory.query.join(Accessory).filter(
        Accessory.user_id == current_user.id,
        BorrowedAccessory.status == 'pending'
    ).all()
    
    # Get approved and delivered requests for items owned by the user
    approved_requests = BorrowedAccessory.query.filter(
        BorrowedAccessory.lender_id == current_user.id,
        BorrowedAccessory.status.in_(['approved', 'delivered'])
    ).all()
    
    return render_template('borrow_requests.html',
                         pending_requests=pending_requests,
                         approved_requests=approved_requests)

@app.route('/approve_borrow/<int:borrow_id>', methods=['POST'])
@login_required
def approve_borrow(borrow_id):
    borrowed_item = BorrowedAccessory.query.get_or_404(borrow_id)
    
    # Check if the current user is the lender
    if borrowed_item.lender_id != current_user.id:
        flash('You are not authorized to approve this request.', 'danger')
        return redirect(url_for('borrow_requests'))
    
    # Get the accessory
    accessory = Accessory.query.get(borrowed_item.accessory_id)
    if not accessory:
        flash('Accessory not found.', 'danger')
        return redirect(url_for('borrow_requests'))
    
    try:
        # Store accessory info for history
        borrowed_item.item_name = accessory.name
        borrowed_item.item_category = accessory.category
        
        # Delete all other pending borrow requests for this accessory
        BorrowedAccessory.query.filter(
            BorrowedAccessory.accessory_id == accessory.id,
            BorrowedAccessory.id != borrowed_item.id,
            BorrowedAccessory.status == 'pending'
        ).delete()
        
        # Update the borrow request status to approved and mark accessory as unavailable
        borrowed_item.status = 'approved'
        borrowed_item.lender_confirmed_delivery = False
        borrowed_item.borrower_confirmed_delivery = False
        accessory.is_available = False
        
        # Create a system message in the chat to inform both parties
        system_message = f"Borrow request for {accessory.name} has been approved by {current_user.username}. You can use this chat to coordinate the handover."
        
        # Add system message from lender to borrower
        chat_message = ChatMessage(
            borrow_id=borrow_id,
            sender_id=current_user.id,
            recipient_id=borrowed_item.borrower_id,
            message=system_message
        )
        
        # Commit all changes
        db.session.add(chat_message)
        db.session.commit()
        
        flash('Borrow request approved successfully. You can now chat with the borrower to coordinate the handover.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the request.', 'danger')
        print(f"Error details: {str(e)}")
    
    # Redirect to chat with show_modal parameter set to trigger the welcome popup
    return redirect(url_for('chat', borrow_id=borrow_id, show_modal=1))

@app.route('/reject_borrow/<int:borrow_id>', methods=['POST'])
@login_required
def reject_borrow(borrow_id):
    borrowed_item = BorrowedAccessory.query.get_or_404(borrow_id)
    if borrowed_item.lender_id != current_user.id:
        flash('You are not authorized to reject this request', 'error')
        return redirect(url_for('borrow_requests'))
    
    # Get the rejection reason
    rejection_reason = request.form.get('rejection_reason', '').strip()
    if not rejection_reason:
        flash('Please provide a reason for rejection', 'error')
        return redirect(url_for('borrow_requests'))
    
    try:
        # Create a record of the rejected request
        rejected_request = RejectedBorrowRequest(
            accessory_id=borrowed_item.accessory_id,
            borrower_id=borrowed_item.borrower_id,
            lender_id=borrowed_item.lender_id,
            pickup_location=borrowed_item.pickup_location,
            pickup_datetime=borrowed_item.pickup_datetime,
            residence=borrowed_item.residence,
            message=borrowed_item.message,
            rejection_reason=rejection_reason,
            created_at=borrowed_item.created_at,
            delivery_preference=borrowed_item.delivery_preference
        )
        
        # Add the rejected request and delete the original
        db.session.add(rejected_request)
        db.session.delete(borrowed_item)
        db.session.commit()
        
        flash('Borrow request rejected and removed', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while rejecting the request', 'error')
        print(f"Error details: {str(e)}")
    
    return redirect(url_for('borrow_requests'))

@app.route('/return_request/<int:borrow_id>')
@login_required
def return_request(borrow_id):
    borrowed_item = BorrowedAccessory.query.filter_by(
        id=borrow_id,
        borrower_id=current_user.id
    ).first_or_404()
    
    # Check if both parties have confirmed delivery
    if not (borrowed_item.lender_confirmed_delivery and borrowed_item.borrower_confirmed_delivery):
        flash('You cannot return an item until both parties have confirmed the delivery', 'warning')
        return redirect(url_for('user_dashboard'))
    
    return render_template('return_request.html', borrowed_item=borrowed_item)

@app.route('/return_item/<int:item_id>', methods=['POST'])
@login_required
def return_item(item_id):
    # Get the borrowed item
    borrowed_item = BorrowedAccessory.query.filter(
        BorrowedAccessory.id == item_id,
        BorrowedAccessory.borrower_id == current_user.id,
        BorrowedAccessory.status.in_(['approved', 'delivered'])
    ).first_or_404()
    
    # Print form data for debugging
    print(f"Return request form data: {request.form}")
    
    # Check if required fields are present
    if not request.form.get('return_location') or not request.form.get('return_datetime'):
        flash('Please fill in all required fields', 'error')
        return redirect(url_for('return_request', borrow_id=item_id))
    
    # Get the accessory to store its name
    accessory = Accessory.query.get(borrowed_item.accessory_id)
    
    # Check if a rejected return request already exists for this item
    existing_return = ReturnedAccessory.query.filter(
        ReturnedAccessory.accessory_id == borrowed_item.accessory_id,
        ReturnedAccessory.borrower_id == current_user.id,
        ReturnedAccessory.status == 'rejected'
    ).first()
    
    try:
        if existing_return:
            # Update the existing return request instead of creating a new one
            existing_return.status = 'pending'
            existing_return.return_location = request.form.get('return_location')
            existing_return.pickup_location = request.form.get('pickup_location', borrowed_item.pickup_location)
            existing_return.return_datetime = request.form.get('return_datetime')  # Store as string
            existing_return.return_notes = request.form.get('return_notes')
            existing_return.created_at = datetime.now()  # Update the timestamp
            existing_return.rejection_reason = None  # Clear previous rejection reason
            existing_return.lender_confirmed_return = False
            existing_return.borrower_confirmed_return = False
            
            print(f"Updating existing return request: {existing_return.id}")
            db.session.commit()
            
            flash('Return request updated and resubmitted. Waiting for lender approval.', 'success')
        else:
            # Create a new return request
            return_request = ReturnedAccessory(
                accessory_id=borrowed_item.accessory_id,
                borrower_id=current_user.id,
                lender_id=borrowed_item.lender_id,
                status='pending',
                return_location=request.form.get('return_location'),
                pickup_location=request.form.get('pickup_location', borrowed_item.pickup_location),
                return_datetime=request.form.get('return_datetime'),
                return_notes=request.form.get('return_notes'),
                item_name=accessory.name if accessory else borrowed_item.item_name
            )
            
            print(f"Creating new return request for item: {borrowed_item.accessory_id}")
            
            # Add the return request
            db.session.add(return_request)
            db.session.commit()
            
            flash('Return request submitted successfully. Waiting for lender approval.', 'success')
        
        # We DON'T delete the borrowed_item record here anymore
        # The item will stay in borrowed state until the return is confirmed
        
        return redirect(url_for('user_dashboard'))
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while submitting your return request: ' + str(e), 'error')
        print(f"Error in return_item: {str(e)}")
        # Return to the form
        return redirect(url_for('return_request', borrow_id=item_id))

@app.route('/approve_return/<int:return_id>', methods=['POST'])
@login_required
def approve_return(return_id):
    return_request = ReturnedAccessory.query.get_or_404(return_id)
    if return_request.lender_id != current_user.id:
        flash('You are not authorized to approve this return', 'error')
        return redirect(url_for('return_requests'))
    
    try:
        # Update return request status to approved
        return_request.status = 'approved'
        db.session.commit()
        
        # Add a system message to the chat
        borrowed_accessory = BorrowedAccessory.query.filter_by(
            accessory_id=return_request.accessory_id,
            borrower_id=return_request.borrower_id,
            lender_id=return_request.lender_id
        ).first()
        
        if borrowed_accessory:
            system_message = f"Return request has been approved. You can now meet to complete the return."
            
            # Create chat message to notify the borrower
            chat_message = ChatMessage(
                borrow_id=borrowed_accessory.id,
                sender_id=current_user.id,
                recipient_id=return_request.borrower_id,
                message=system_message
            )
            
            db.session.add(chat_message)
            db.session.commit()
        
        flash('Return request approved. Please meet with the borrower to complete the return.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the request: ' + str(e), 'error')
        print(f"Error in approve_return: {str(e)}")
    
    return redirect(url_for('return_requests'))

@app.route('/reject_return/<int:return_id>', methods=['POST'])
@login_required
def reject_return(return_id):
    return_request = ReturnedAccessory.query.get_or_404(return_id)
    
    # Make sure current user is the lender
    if return_request.lender_id != current_user.id:
        flash('You are not authorized to reject this return request.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    # Get the borrowed accessory
    borrowed_accessory = BorrowedAccessory.query.filter_by(
        accessory_id=return_request.accessory_id,
        borrower_id=return_request.borrower_id,
        lender_id=return_request.lender_id
    ).first()
    
    if not borrowed_accessory:
        flash('Associated borrow record not found.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    rejection_reason = request.form.get('rejection_reason', '')
    
    try:
        # Update return request status
        return_request.status = 'rejected'
        return_request.rejection_reason = rejection_reason
        
        db.session.commit()
        
        # Create a system notification in the chat about the rejection
        if borrowed_accessory:
            system_message = f"Return request was rejected. Reason: {rejection_reason}"
            
            # Create chat message to notify the borrower
            chat_message = ChatMessage(
                borrow_id=borrowed_accessory.id,
                sender_id=current_user.id,
                recipient_id=return_request.borrower_id,
                message=system_message
            )
            
            db.session.add(chat_message)
            db.session.commit()
        
        flash('Return request rejected successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while rejecting the request.', 'danger')
        print(f"Error details: {str(e)}")
    
    # Redirect to chat with the borrower instead of dashboard
    return redirect(url_for('chat', borrow_id=borrowed_accessory.id, show_modal=1))

@app.route('/lender_dashboard')
@login_required
def lender_dashboard():
    # Get items owned by the current user
    my_items = Accessory.query.filter_by(user_id=current_user.id).all()
    
    # Get borrow requests for the user's items
    borrow_requests = BorrowedAccessory.query.filter_by(lender_id=current_user.id).all()
    
    return render_template('lender_dashboard.html', 
                         my_items=my_items,
                         borrow_requests=borrow_requests)

@app.route('/return_requests')
@login_required
def return_requests():
    # Get pending return requests for items owned by the user (as lender)
    pending_returns_as_lender = ReturnedAccessory.query.filter(
        ReturnedAccessory.lender_id == current_user.id,
        ReturnedAccessory.status == 'pending'
    ).all()
    
    # Get approved return requests for items owned by the user (as lender)
    approved_returns_as_lender = ReturnedAccessory.query.filter(
        ReturnedAccessory.lender_id == current_user.id,
        ReturnedAccessory.status == 'approved'
    ).all()
    
    # Get rejected return requests for items owned by the user (as lender)
    rejected_returns_as_lender = ReturnedAccessory.query.filter(
        ReturnedAccessory.lender_id == current_user.id,
        ReturnedAccessory.status == 'rejected'
    ).all()
    
    # Get pending return requests made by the user (as borrower)
    pending_returns_as_borrower = ReturnedAccessory.query.filter(
        ReturnedAccessory.borrower_id == current_user.id,
        ReturnedAccessory.status == 'pending'
    ).all()
    
    # Get approved return requests made by the user (as borrower)
    approved_returns_as_borrower = ReturnedAccessory.query.filter(
        ReturnedAccessory.borrower_id == current_user.id,
        ReturnedAccessory.status == 'approved'
    ).all()
    
    # Get rejected return requests made by the user (as borrower)
    rejected_returns_as_borrower = ReturnedAccessory.query.filter(
        ReturnedAccessory.borrower_id == current_user.id,
        ReturnedAccessory.status == 'rejected'
    ).all()
    
    # Determine if current user is a lender or borrower for these returns
    is_lender = current_user.id in [r.lender_id for r in pending_returns_as_lender + approved_returns_as_lender]
    is_borrower = current_user.id in [r.borrower_id for r in pending_returns_as_borrower + approved_returns_as_borrower]
    
    return render_template('return_requests.html',
                         pending_returns=pending_returns_as_lender + pending_returns_as_borrower,
                         approved_returns=approved_returns_as_lender + approved_returns_as_borrower,
                         rejected_returns=rejected_returns_as_lender + rejected_returns_as_borrower,
                         is_lender=is_lender,
                         is_borrower=is_borrower)

@app.route('/borrow_history')
@login_required
def borrow_history():
    # Get items borrowed by the user
    borrowed_history = BorrowHistory.query.filter_by(borrower_id=current_user.id).order_by(BorrowHistory.return_date.desc()).all()
    
    # Get items lent by the user
    lent_history = BorrowHistory.query.filter_by(lender_id=current_user.id).order_by(BorrowHistory.return_date.desc()).all()
    
    return render_template('borrow_history.html', 
                         borrowed_history=borrowed_history,
                         lent_history=lent_history)

@app.route('/confirm_lender_delivery/<int:borrow_id>', methods=['POST'])
@login_required
def confirm_lender_delivery(borrow_id):
    borrow_request = BorrowedAccessory.query.get_or_404(borrow_id)
    
    # Verify that the current user is the lender
    if borrow_request.lender_id != current_user.id:
        flash('You are not authorized to confirm this delivery', 'danger')
        return redirect(url_for('borrow_requests'))
    
    # Update the lender confirmation status
    borrow_request.lender_confirmed_delivery = True
    
    # Check if both lender and borrower have confirmed
    if borrow_request.borrower_confirmed_delivery:
        borrow_request.status = 'delivered'
        flash('Delivery completed! Both parties have confirmed the handover.', 'success')
    else:
        flash('You have confirmed the item handover. Waiting for borrower confirmation.', 'success')
    
    db.session.commit()
    return redirect(url_for('borrow_requests'))

@app.route('/confirm_borrower_delivery/<int:borrow_id>', methods=['POST'])
@login_required
def confirm_borrower_delivery(borrow_id):
    borrow_request = BorrowedAccessory.query.get_or_404(borrow_id)
    
    # Verify that the current user is the borrower
    if borrow_request.borrower_id != current_user.id:
        flash('You are not authorized to confirm this delivery', 'danger')
        return redirect(url_for('user_dashboard'))
    
    # Update the borrower confirmation status
    borrow_request.borrower_confirmed_delivery = True
    
    # Check if both lender and borrower have confirmed
    if borrow_request.lender_confirmed_delivery:
        borrow_request.status = 'delivered'
        flash('Delivery completed! Both parties have confirmed the handover.', 'success')
    else:
        flash('You have confirmed receipt of the item. Waiting for lender confirmation.', 'success')
    
    db.session.commit()
    return redirect(url_for('user_dashboard'))

@app.route('/confirm_return/<int:return_id>', methods=['POST'])
@login_required
def confirm_return(return_id):
    return_request = ReturnedAccessory.query.get_or_404(return_id)
    
    # Check if the current user is either the borrower or the lender
    if current_user.id == return_request.borrower_id:
        return_request.borrower_confirmed_return = True
        flash('You have confirmed the item return', 'success')
    elif current_user.id == return_request.lender_id:
        return_request.lender_confirmed_return = True
        flash('You have confirmed the item return', 'success')
    else:
        flash('You are not authorized to confirm this return', 'error')
        return redirect(url_for('return_requests'))
    
    # If both parties confirmed, complete the return process
    if return_request.borrower_confirmed_return and return_request.lender_confirmed_return:
        try:
            # Get the accessory
            accessory = Accessory.query.get(return_request.accessory_id)
            
            if accessory:
                # Create history entry
                history = BorrowHistory(
                    item_name=return_request.item_name,
                    item_category=accessory.category,
                    borrower_id=return_request.borrower_id,
                    lender_id=return_request.lender_id,
                    borrow_date=return_request.created_at,
                    return_date=func.now(),
                    pickup_location=return_request.pickup_location,
                    return_location=return_request.return_location
                )
                
                # Add to history
                db.session.add(history)
                
                # Update return request status but DON'T automatically make accessory available again
                return_request.status = 'delivered'
                
                # Instead of deleting rejected returns, get all return requests for this item and borrower
                # and mark all of them as completed or delete the rejected ones
                other_returns = ReturnedAccessory.query.filter(
                    ReturnedAccessory.accessory_id == return_request.accessory_id,
                    ReturnedAccessory.borrower_id == return_request.borrower_id,
                    ReturnedAccessory.id != return_request.id  # Exclude the current request
                ).all()
                
                for other_return in other_returns:
                    if other_return.status == 'rejected':
                        # Delete rejected return requests for this item
                        db.session.delete(other_return)
                    else:
                        # Mark any other pending or approved returns as 'delivered' as well
                        other_return.status = 'delivered'
                
                # Find the original borrow request and archive its chat messages
                borrow_request = BorrowedAccessory.query.filter_by(
                    accessory_id=return_request.accessory_id,
                    borrower_id=return_request.borrower_id,
                    lender_id=return_request.lender_id
                ).first()
                
                if borrow_request:
                    # Instead of deleting chat messages, archive them or simply change the foreign key to NULL
                    # First, export/archive the chat messages if needed (omitted for brevity)
                    
                    # Option 1: Set borrow_id to NULL if your database schema allows it
                    # ChatMessage.query.filter_by(borrow_id=borrow_request.id).update({'borrow_id': None})
                    
                    # Option 2: Delete chat messages
                    ChatMessage.query.filter_by(borrow_id=borrow_request.id).delete()
                    
                    # Now we can safely delete the borrowed accessory
                    db.session.delete(borrow_request)
                
                db.session.commit()
                flash('Return completed successfully', 'success')
                
                # If the current user is the lender, redirect to the relist choice page
                if current_user.id == return_request.lender_id:
                    return redirect(url_for('relist_choice', accessory_id=accessory.id))
                    
                # Otherwise just redirect to the return requests page
                return redirect(url_for('return_requests'))
            else:
                flash('Accessory not found', 'error')
                
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while completing the return: ' + str(e), 'danger')
            print(f"Error in confirm_return: {str(e)}")
    else:
        db.session.commit()
    
    return redirect(url_for('return_requests'))

@app.route('/relist_choice/<int:accessory_id>', methods=['GET', 'POST'])
@login_required
def relist_choice(accessory_id):
    accessory = Accessory.query.get_or_404(accessory_id)
    
    # Ensure the current user is the owner of the accessory
    if accessory.user_id != current_user.id:
        flash('You are not authorized to make decisions for this item', 'error')
        return redirect(url_for('user_dashboard'))
    
    if request.method == 'POST':
        choice = request.form.get('choice')
        
        if choice == 'relist':
            # Make the item available again
            accessory.is_available = True
            db.session.commit()
            flash('Your item has been relisted and is now available for others to borrow!', 'success')
        elif choice == 'keep':
            # Keep the item unavailable
            accessory.is_available = False
            db.session.commit()
            flash('You have chosen to keep your item. It will not be available for others to borrow.', 'success')
        else:
            flash('Invalid choice. Please select either "Relist Item" or "Keep Item".', 'warning')
            return redirect(url_for('relist_choice', accessory_id=accessory.id))
            
        return redirect(url_for('user_dashboard'))
    
    return render_template('relist_choice.html', accessory=accessory)

@app.route('/relist_item/<int:item_id>', methods=['POST'])
@login_required
def relist_item(item_id):
    """Route to directly relist an item from the dashboard"""
    accessory = Accessory.query.get_or_404(item_id)
    
    # Ensure the current user is the owner of the accessory
    if accessory.user_id != current_user.id:
        flash('You are not authorized to modify this item', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Make the item available again
    accessory.is_available = True
    db.session.commit()
    flash('Your item has been relisted and is now available for others to borrow!', 'success')
    
    return redirect(url_for('user_dashboard'))

@app.route('/borrow_details/<int:borrow_id>')
@login_required
def borrow_details(borrow_id):
    """View details of a specific borrow request"""
    borrow_request = BorrowedAccessory.query.get_or_404(borrow_id)
    
    # Ensure the current user is either the borrower or the lender
    if current_user.id != borrow_request.borrower_id and current_user.id != borrow_request.lender_id:
        flash('You are not authorized to view this borrow request', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Add the item for consistency with the borrow_item route
    item = borrow_request.accessory
    
    return render_template('borrow_details.html', borrow_request=borrow_request, item=item)

@app.route('/chat/<int:borrow_id>', methods=['GET', 'POST'])
@login_required
def chat(borrow_id):
    """Chat between borrower and lender for a specific borrow request"""
    borrow_request = BorrowedAccessory.query.get_or_404(borrow_id)
    
    # Ensure the current user is either the borrower or the lender
    if current_user.id != borrow_request.borrower_id and current_user.id != borrow_request.lender_id:
        flash('You are not authorized to access this chat', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Flag to show the welcome modal (triggered after approval or via URL parameter)
    show_modal = request.args.get('show_modal') == '1'
    
    # Handle sending new messages
    if request.method == 'POST':
        message_text = request.form.get('message', '').strip()
        if message_text:
            # Determine the recipient (the other person in the conversation)
            recipient_id = borrow_request.lender_id if current_user.id == borrow_request.borrower_id else borrow_request.borrower_id
            
            # Create new message
            new_message = ChatMessage(
                borrow_id=borrow_id,
                sender_id=current_user.id,
                recipient_id=recipient_id,
                message=message_text
            )
            
            db.session.add(new_message)
            db.session.commit()
            
            flash('Message sent', 'success')
            return redirect(url_for('chat', borrow_id=borrow_id))
    
    # Get all messages for this borrow request
    messages = ChatMessage.query.filter_by(borrow_id=borrow_id).order_by(ChatMessage.timestamp).all()
    
    # Mark all messages to the current user as read
    unread_messages = ChatMessage.query.filter_by(
        borrow_id=borrow_id, 
        recipient_id=current_user.id,
        is_read=False
    ).all()
    
    for msg in unread_messages:
        msg.is_read = True
    
    db.session.commit()
    
    # Calculate today and yesterday for date display in the template
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    return render_template('chat.html', 
                         borrow_request=borrow_request, 
                         messages=messages,
                         today=today,
                         yesterday=yesterday,
                         show_modal=show_modal)

@app.route('/chat_history')
@login_required
def chat_history():
    """View all active chat conversations"""
    # Get all borrow requests where the user is either borrower or lender
    borrower_requests = BorrowedAccessory.query.filter(
        BorrowedAccessory.borrower_id == current_user.id,
        BorrowedAccessory.status.in_(['pending', 'approved', 'delivered'])
    ).all()
    
    lender_requests = BorrowedAccessory.query.filter(
        BorrowedAccessory.lender_id == current_user.id,
        BorrowedAccessory.status.in_(['pending', 'approved', 'delivered'])
    ).all()
    
    # Combine and sort by last message date
    active_chats = []
    
    for request in borrower_requests + lender_requests:
        last_message = ChatMessage.query.filter_by(borrow_id=request.id).order_by(ChatMessage.timestamp.desc()).first()
        
        # Count unread messages
        unread_count = ChatMessage.query.filter_by(
            borrow_id=request.id,
            recipient_id=current_user.id,
            is_read=False
        ).count()
        
        active_chats.append({
            'borrow_request': request,
            'last_message': last_message,
            'unread_count': unread_count
        })
    
    # Sort chats by most recent message first
    active_chats.sort(
        key=lambda x: x['last_message'].timestamp if x['last_message'] else datetime.min,
        reverse=True
    )
    
    return render_template('chat_history.html', active_chats=active_chats)

if __name__ == '__main__':
    with app.app_context():
        create_tables_and_admin()  # Only creates tables if they don't exist
    app.run()
