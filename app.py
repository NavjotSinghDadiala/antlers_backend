from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from os import environ
import random
import threading
from dotenv import load_dotenv
import requests
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


app = Flask(__name__)

# Configure secret key
app.config['SECRET_KEY'] = 'antlers-secret-key-2003'

# Configure database
instance_path = os.path.join(app.root_path, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)
db_path = os.path.join(instance_path, 'antlers.db')
if 'DATABASE_URL' in environ:
    app.config['SQLALCHEMY_DATABASE_URI'] = environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure upload folder for images
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app) 
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

load_dotenv()
import os

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
    overall_verified = db.Column(db.Boolean, default=False)
    
    # Relationships
    approved_items = db.relationship('Accessory', 
                                   foreign_keys='Accessory.user_id',
                                   backref=db.backref('owner', lazy=True))
    
    # Borrowed items (items this user has borrowed)
    items_borrowed = db.relationship('BorrowedAccessory',
                                   foreign_keys='BorrowedAccessory.borrower_id',
                                   backref=db.backref('borrower_user', lazy=True),
                                   overlaps="items_borrowed_as_borrower,borrower")
    
    # Lent items (items this user has lent to others)
    items_lent = db.relationship('BorrowedAccessory',
                                foreign_keys='BorrowedAccessory.lender_id',
                                backref=db.backref('lender_user', lazy=True),
                                overlaps="items_lent_as_lender,lender")

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
    borrower = db.relationship('User', foreign_keys=[borrower_id], backref='items_borrowed_as_borrower', overlaps="items_borrowed,borrower_user")
    lender = db.relationship('User', foreign_keys=[lender_id], backref='items_lent_as_lender', overlaps="items_lent,lender_user")

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

class CommunityChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=func.now())
    
    # Relationships
    user = db.relationship('User', backref=db.backref('community_messages', lazy=True))

class SwapItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    condition = db.Column(db.String(20), nullable=False)
    image = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, completed
    created_at = db.Column(db.DateTime, default=func.now())
    rejection_reason = db.Column(db.Text)
    received_item_id = db.Column(db.Integer, db.ForeignKey('swap_item.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    meeting_link = db.Column(db.String(255))
    meeting_scheduled = db.Column(db.Boolean, default=False)
    meeting_time = db.Column(db.DateTime)
    delivery_completed = db.Column(db.Boolean, default=False)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('swap_items', lazy=True), foreign_keys=[user_id])
    received_item = db.relationship('SwapItem', remote_side=[id])
    recipient = db.relationship('User', backref=db.backref('received_swap_items', lazy=True), foreign_keys=[recipient_id])

class SwapEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # pending, active, completed
    created_at = db.Column(db.DateTime, default=func.now())
    is_weekly = db.Column(db.Boolean, default=True)
    # For weekly events, we'll automatically create new ones
    scheduled_day = db.Column(db.String(10), default='Saturday')  # Day of the week for scheduled events
    
    # Relationships
    items = db.relationship('SwapItem', secondary='swap_event_items', backref=db.backref('events', lazy=True))

# Association table for SwapEvent and SwapItem
swap_event_items = db.Table('swap_event_items',
    db.Column('event_id', db.Integer, db.ForeignKey('swap_event.id'), primary_key=True),
    db.Column('item_id', db.Integer, db.ForeignKey('swap_item.id'), primary_key=True)
)

class GameChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    swap_item_id = db.Column(db.Integer, db.ForeignKey('swap_item.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=func.now())
    is_read = db.Column(db.Boolean, default=False)

    # Relationships
    swap_item = db.relationship('SwapItem', backref=db.backref('game_chat_messages', lazy=True, order_by='GameChatMessage.timestamp'))
    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_game_messages', lazy=True))
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref=db.backref('received_game_messages', lazy=True))

class GameCommunityMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    swap_event_id = db.Column(db.Integer, db.ForeignKey('swap_event.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=func.now())
    
    # Relationships
    user = db.relationship('User', backref=db.backref('game_community_messages', lazy=True))
    swap_event = db.relationship('SwapEvent', backref=db.backref('community_messages', lazy=True))

# Function to create tables and the admin user
def create_tables_and_admin():
    db.create_all()  # Creates tables if they don't exist
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='antlers@admin2003', role='admin' , email='23f2000835@ds.study.iitm.ac.in')
        db.session.add(admin)
        db.session.commit()
    
    # Create a default swap event if none exists
    if not SwapEvent.query.first():
        from datetime import datetime, timedelta
        default_event = SwapEvent(
            name='Weekly Swap Meet',
            description='Join our weekly community swap event! Share items and connect with others.',
            start_date=datetime.now() + timedelta(days=7),
            end_date=datetime.now() + timedelta(days=7, hours=2),
            status='active',
            is_weekly=True,
            scheduled_day='Saturday'
        )
        db.session.add(default_event)
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
    # Only show items that are available and are for lending (not donations)
    items = Accessory.query.filter_by(is_available=True, type='lend').all()
    return render_template('home.html', items=items)

@app.route('/what-we-offer')
def what_we_offer():
    """Render the 'What We Offer' page"""
    return render_template('what_we_offer.html')

@app.route('/how-it-works')
def how_it_works():
    """Render the 'How It Works' page"""
    return render_template('how_it_works.html')

@app.route('/community', methods=['GET', 'POST'])
def community():
    """Community chat page"""
    if request.method == 'POST' and current_user.is_authenticated:
        message = request.form.get('message')
        if message:
            new_message = CommunityChatMessage(
                user_id=current_user.id,
                message=message
            )
            db.session.add(new_message)
            db.session.commit()
            flash('Message sent successfully!', 'success')
            # Email all users (except sender) about new community message
            recipients = [u.email for u in User.query.filter(User.id != current_user.id, User.overall_verified == True).all() if u.email]
            if recipients:
                subject = f"New Community Message from {current_user.username}"
                body = f"<p><b>{current_user.username}</b> posted in the community chat:</p><blockquote>{message}</blockquote>"
                for email in recipients:
                    send_notification_email(email, subject, body)
            return redirect(url_for('community'))
    
    # Get all community messages
    messages = CommunityChatMessage.query.order_by(CommunityChatMessage.timestamp.desc()).limit(50).all()
    messages.reverse()  # Show oldest first
    
    return render_template('community.html', messages=messages)

@app.route('/delete_community_message/<int:message_id>', methods=['POST'])
@login_required
def delete_community_message(message_id):
    """Delete a community message (admin only)"""
    if current_user.role != 'admin':
        flash('You do not have permission to delete messages.', 'danger')
        return redirect(url_for('community'))
    
    message = CommunityChatMessage.query.get_or_404(message_id)
    db.session.delete(message)
    db.session.commit()
    flash('Message deleted successfully.', 'success')
    return redirect(url_for('community'))

@app.route('/game_selection')
def game_selection():
    """Game selection page"""
    # Get participant count for display
    participant_count = SwapItem.query.count()
    return render_template('game_selection.html', participant_count=participant_count)

@app.route('/games')
def games():
    """Games page - Swap game interface"""
    # Get upcoming swap event
    upcoming_swap = SwapEvent.query.filter_by(status='active').first()
    
    # Get recent swaps
    recent_swaps = SwapItem.query.filter_by(status='completed').order_by(SwapItem.created_at.desc()).limit(6).all()
    
    # Get participant count
    participant_count = SwapItem.query.count()
    
    return render_template('games.html', 
                         upcoming_swap=upcoming_swap,
                         recent_swaps=recent_swaps,
                         participant_count=participant_count)

@app.route('/submit_swap_item', methods=['GET', 'POST'])
@login_required
def submit_swap_item():
    """Submit a swap item"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category = request.form.get('category')
        condition = request.form.get('condition')
        image = request.files.get('image')
        
        if image and allowed_file(image.filename):
            filename = save_file(image)
        else:
            flash('Please provide a valid image file.', 'danger')
            return redirect(url_for('games'))
        
        swap_item = SwapItem(
            name=name,
            description=description,
            category=category,
            condition=condition,
            image=filename,
            user_id=current_user.id
        )
        
        db.session.add(swap_item)
        db.session.commit()
        
        flash('Swap item submitted successfully!', 'success')
        return redirect(url_for('games'))
    
    return redirect(url_for('games'))

@app.route('/game_community/<int:event_id>')
@login_required
def game_community(event_id):
    """Game community chat page"""
    try:
        swap_event = SwapEvent.query.get_or_404(event_id)
        messages = GameCommunityMessage.query.filter_by(swap_event_id=event_id).order_by(GameCommunityMessage.timestamp.desc()).limit(50).all()
        messages.reverse()
        
        return render_template('game_community.html', swap_event=swap_event, messages=messages)
    except Exception as e:
        app.logger.error(f"Error in game_community route for event_id {event_id}: {str(e)}")
        flash('Event not found or an error occurred. Please check if the event exists.', 'danger')
        return redirect(url_for('games'))

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    # Get user's items and swap items for display
    user_items = Accessory.query.filter_by(user_id=current_user.id).all()
    swap_items = SwapItem.query.filter_by(user_id=current_user.id).all()
    
    # Get swap items received by the user
    received_swap_items = SwapItem.query.filter_by(recipient_id=current_user.id).all()
    
    return render_template('profile.html', user_items=user_items, swap_items=swap_items, received_swap_items=received_swap_items)

@app.route('/chat_history')
@login_required
def chat_history():
    """Chat history page"""
    # Get all borrow requests where user is borrower or lender
    from sqlalchemy import or_
    borrow_requests = BorrowedAccessory.query.filter(
        or_(BorrowedAccessory.borrower_id == current_user.id, BorrowedAccessory.lender_id == current_user.id)
    ).all()
    
    # Create active_chats list with chat information
    active_chats = []
    for borrow_request in borrow_requests:
        # Get the last message for this borrow request
        last_message = ChatMessage.query.filter_by(borrow_id=borrow_request.id).order_by(ChatMessage.timestamp.desc()).first()
        
        # Count unread messages for current user
        unread_count = ChatMessage.query.filter_by(
            borrow_id=borrow_request.id,
            recipient_id=current_user.id,
            is_read=False
        ).count()
        
        active_chats.append({
            'borrow_request': borrow_request,
            'last_message': last_message,
            'unread_count': unread_count
        })
    
    # Sort by last message timestamp (most recent first)
    active_chats.sort(key=lambda x: x['last_message'].timestamp if x['last_message'] else x['borrow_request'].created_at, reverse=True)
    
    # Add date variables for template
    from datetime import date
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    return render_template('chat_history.html', active_chats=active_chats, today=today, yesterday=yesterday)

@app.route('/borrow_details/<int:borrow_id>')
@login_required
def borrow_details(borrow_id):
    """Borrow request details page"""
    borrow_request = BorrowedAccessory.query.get_or_404(borrow_id)
    
    # Check if user is authorized to view this request
    if borrow_request.borrower_id != current_user.id and borrow_request.lender_id != current_user.id:
        flash('You are not authorized to view this request.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    # Get chat messages for this borrow request
    chat_messages = ChatMessage.query.filter_by(borrow_id=borrow_id).order_by(ChatMessage.timestamp).all()
    
    return render_template('borrow_details.html', borrow_request=borrow_request, chat_messages=chat_messages)

@app.route('/relist_item/<int:item_id>', methods=['POST'])
@login_required
def relist_item(item_id):
    """Relist an item"""
    item = Accessory.query.get_or_404(item_id)
    # Check if user owns this item
    if item.user_id != current_user.id:
        flash('You are not authorized to relist this item.', 'danger')
        return redirect(url_for('user_dashboard'))
    # Create a new pending item 
    pending_item = PendingAccessory(
        name=item.name,
        description=item.description,
        category=item.category,
        location=item.location,
        image=item.image,
        type=item.type,
        user_id=current_user.id,
        residence=current_user.residence if hasattr(current_user, 'residence') else ''
    )
    db.session.add(pending_item)
    db.session.delete(item)
    db.session.commit()
    flash('Item relisted successfully!', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    """Delete an item"""
    item = Accessory.query.get_or_404(item_id)
    
    # Check if user owns this item
    if item.user_id != current_user.id:
        flash('You are not authorized to delete this item.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    db.session.delete(item)
    db.session.commit()
    
    flash('Item deleted successfully!', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/swap_item_details/<int:item_id>')
@login_required
def swap_item_details(item_id):
    """Swap item details page"""
    swap_item = SwapItem.query.get_or_404(item_id)
    return render_template('swap_item_details.html', item=swap_item)

@app.route('/schedule_swap_meeting/<int:item_id>', methods=['GET', 'POST'])
@login_required
def schedule_swap_meeting(item_id):
    """Schedule a swap meeting"""
    swap_item = SwapItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        meeting_link = request.form.get('meeting_link')
        meeting_time = request.form.get('meeting_time')
        
        if meeting_link and meeting_time:
            swap_item.meeting_link = meeting_link
            swap_item.meeting_time = datetime.strptime(meeting_time, '%Y-%m-%dT%H:%M')
            swap_item.meeting_scheduled = True
            db.session.commit()
            
            flash('Meeting scheduled successfully!', 'success')
            return redirect(url_for('swap_item_details', item_id=item_id))
        else:
            flash('Please provide both meeting link and time.', 'danger')
    
    return render_template('schedule_swap_meeting.html', item=swap_item)

@app.route('/confirm_swap_delivery/<int:item_id>', methods=['POST'])
@login_required
def confirm_swap_delivery(item_id):
    """Confirm swap delivery"""
    swap_item = SwapItem.query.get_or_404(item_id)
    
    # Check if user is the recipient
    if swap_item.recipient_id != current_user.id:
        flash('You are not authorized to confirm this delivery.', 'danger')
        return redirect(url_for('swap_item_details', item_id=item_id))
    
    swap_item.delivery_completed = True
    swap_item.status = 'completed'
    db.session.commit()
    
    flash('Delivery confirmed! Swap completed successfully.', 'success')
    return redirect(url_for('swap_item_details', item_id=item_id))

@app.route('/my_swap_items')
@login_required
def my_swap_items():
    """User's swap items page"""
    # Get user's swap items
    my_swap_items = SwapItem.query.filter_by(user_id=current_user.id).all()
    
    # Get swap items received by the user
    received_swap_items = SwapItem.query.filter_by(recipient_id=current_user.id).all()
    
    return render_template('my_swap_items.html', 
                         my_swap_items=my_swap_items,
                         received_swap_items=received_swap_items)

@app.route('/confirm_return/<int:return_id>', methods=['POST'])
@login_required
def confirm_return(return_id):
    """Confirm return completion"""
    return_request = ReturnedAccessory.query.get_or_404(return_id)
    
    # Check if user is authorized to confirm this return
    if return_request.lender_id != current_user.id and return_request.borrower_id != current_user.id:
        flash('You are not authorized to confirm this return.', 'danger')
        return redirect(url_for('return_requests'))
    
    if return_request.lender_id == current_user.id:
        return_request.lender_confirmed_return = True
    else:
        return_request.borrower_confirmed_return = True
    
    # If both parties have confirmed, mark as completed
    if return_request.lender_confirmed_return and return_request.borrower_confirmed_return:
        return_request.status = 'completed'
        
        # Update the borrowed item status
        borrowed_item = BorrowedAccessory.query.filter_by(
            accessory_id=return_request.accessory_id,
            borrower_id=return_request.borrower_id,
            lender_id=return_request.lender_id
        ).first()
        
        if borrowed_item:
            borrowed_item.status = 'returned'
    
    db.session.commit()
    flash('Return confirmed successfully!', 'success')
    return redirect(url_for('return_requests'))

# Gmail OTP Email Service
class GmailOTPService:
    def __init__(self):
        self.email = os.getenv('GMAIL_USER')
        self.password = os.getenv('GMAIL_PASS')

    def send_otp(self, to_email, otp):
        if not self.email or not self.password:
            return False, "Gmail credentials not configured."
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = to_email
            msg['Subject'] = 'Your Antlers OTP Verification Code'
            body = f"""
            <h2>Antlers OTP Verification</h2>
            <p>Your OTP is: <b>{otp}</b></p>
            <p>This OTP is valid for 5 minutes. Do not share it with anyone.</p>
            """
            msg.attach(MIMEText(body, 'html'))
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email, self.password)
            server.sendmail(self.email, to_email, msg.as_string())
            server.quit()
            return True, "OTP sent successfully to your email."
        except Exception as e:
            return False, f"Failed to send OTP email: {str(e)}"

gmail_otp_service = GmailOTPService()

def send_otp_email(email, otp):
    success, message = gmail_otp_service.send_otp(email, otp)
    if not success:
        print(f"Email send error: {message}")
    return success

# Registration route (update to not log in, redirect to verify)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        contact_number = request.form['contact_number']
        # ... (add any other fields)
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username or email already exists', 'danger')
            return redirect(url_for('register'))
        user = User(username=username, password=password, email=email, contact_number=contact_number, overall_verified=False)
        db.session.add(user)
        db.session.commit()
        session['pending_user_id'] = user.id
        return redirect(url_for('verify'))
    return render_template('register.html')

# OTP verification route (now email-based)
@app.route('/verify', methods=['GET', 'POST'])
def verify():
    user_id = session.get('pending_user_id')
    if not user_id:
        flash('No user to verify. Please register first.', 'danger')
        return redirect(url_for('register'))
    user = User.query.get(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('register'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'resend':
            otp = f"{random.randint(100000, 999999)}"
            session['otp'] = otp
            session['otp_time'] = time.time()
            success, message = gmail_otp_service.send_otp(user.email, otp)
            if success:
                flash(f'New OTP sent to {user.email}.', 'success')
            else:
                flash(f'Failed to send OTP: {message}. Please try again.', 'warning')
            return redirect(url_for('verify'))
        elif action == 'verify':
            otp_entered = request.form.get('otp')
            otp_stored = session.get('otp')
            otp_time = session.get('otp_time')
            if not otp_stored or not otp_time:
                flash('OTP expired. Please request a new one.', 'danger')
                return redirect(url_for('verify'))
            if time.time() - otp_time > 300:
                flash('OTP expired. Please request a new one.', 'danger')
                return redirect(url_for('verify'))
            if otp_entered == otp_stored:
                user.overall_verified = True
                db.session.commit()
                session.pop('otp', None)
                session.pop('otp_time', None)
                session.pop('pending_user_id', None)
                flash('Email verified successfully! You can now log in.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Incorrect OTP. Please try again.', 'danger')
                return redirect(url_for('verify'))
    # On GET, generate/send OTP if not present or expired
    otp = session.get('otp')
    otp_time = session.get('otp_time')
    if not otp or not otp_time or time.time() - otp_time > 300:
        otp = f"{random.randint(100000, 999999)}"
        session['otp'] = otp
        session['otp_time'] = time.time()
        success, message = gmail_otp_service.send_otp(user.email, otp)
        if success:
            flash(f'OTP sent to {user.email}. Please check your email.', 'success')
        else:
            flash(f'Failed to send OTP: {message}. Please try again.', 'danger')
    return render_template('verify.html', email=user.email, user=user)

# Login route (update to check overall_verified)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            if not user.overall_verified:
                session['pending_user_id'] = user.id
                flash('Please verify your email before logging in.', 'warning')
                return redirect(url_for('verify'))
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid credentials', 'danger')
            return redirect(url_for('login'))
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
    my_approved_items = Accessory.query.filter_by(user_id=current_user.id, is_available=True).all()
    my_pending_items = PendingAccessory.query.filter_by(user_id=current_user.id).all()
    
    # Get items borrowed by the user
    borrowed_items = BorrowedAccessory.query.filter_by(borrower_id=current_user.id).all()
    
    # Get items lent by the user
    lent_items = BorrowedAccessory.query.filter_by(lender_id=current_user.id).all()
    
    # Get swap items submitted by the user
    swap_items = SwapItem.query.filter_by(user_id=current_user.id).all()
    
    # Get swap items received by the user (including completed events)
    received_swap_items = SwapItem.query.filter_by(recipient_id=current_user.id).all()
    
    # Get completed swap events where the user participated
    completed_events = SwapEvent.query.filter(
        SwapEvent.status == 'completed',
        SwapEvent.items.any(
            (SwapItem.user_id == current_user.id) | (SwapItem.recipient_id == current_user.id)
        )
    ).all()

    # Calculate stats
    stats = {
        'my_items': len(my_approved_items) + len(my_pending_items),
        'active_borrows': len([b for b in borrowed_items if b.status in ['approved', 'delivered']]),
        'pending_requests': len([b for b in borrowed_items if b.status == 'pending']),
        'swap_items': len(swap_items) + len(received_swap_items)
    }
    
    # Get rejected items
    my_rejected_items = RejectedAccessory.query.filter_by(user_id=current_user.id).all()
    
    # Get rejected borrow requests where the user is the borrower
    my_rejected_borrow_requests = RejectedBorrowRequest.query.filter_by(borrower_id=current_user.id).all()
    
    # Counts for quick links
    chat_history_count = 0
    borrow_requests_count = 0
    return_requests_count = 0
    try:
        from sqlalchemy import or_
        # Chat history: count all borrow requests where user is borrower or lender
        chat_history_count = BorrowedAccessory.query.filter(
            or_(BorrowedAccessory.borrower_id == current_user.id, BorrowedAccessory.lender_id == current_user.id)
        ).count()
        # Borrow requests: count all where user is lender
        borrow_requests_count = BorrowedAccessory.query.filter_by(lender_id=current_user.id).count()
        # Return requests: count all where user is lender or borrower in ReturnedAccessory
        return_requests_count = ReturnedAccessory.query.filter(
            or_(ReturnedAccessory.lender_id == current_user.id, ReturnedAccessory.borrower_id == current_user.id)
        ).count()
    except Exception:
        pass
    
    # Get returned items where the user is the lender and return is completed
    returned_items = ReturnedAccessory.query.filter_by(lender_id=current_user.id, status='completed').all()
    
    return render_template('user_dashboard.html', 
                         my_approved_items=my_approved_items,
                         my_pending_items=my_pending_items,
                         my_rejected_items=my_rejected_items,
                         my_rejected_borrow_requests=my_rejected_borrow_requests,
                         borrowed_items=borrowed_items,
                         lent_items=lent_items,
                         swap_items=swap_items,
                         received_swap_items=received_swap_items,
                         completed_events=completed_events,
                         stats=stats,
                         chat_history_count=chat_history_count,
                         borrow_requests_count=borrow_requests_count,
                         return_requests_count=return_requests_count,
                         returned_items=returned_items)

@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard page"""
    if current_user.role != 'admin':
        flash('You do not have permission to access the admin dashboard.', 'danger')
        return redirect(url_for('home'))
    
    # Get pending items
    pending_items = PendingAccessory.query.all()
    
    # Get rejected items
    rejected_items = RejectedAccessory.query.all()
    
    # Get approved items
    approved_items = Accessory.query.all()
    
    # Get pending swap items
    pending_swap_items = SwapItem.query.filter_by(status='pending').count()
    
    # Get active swap events
    active_swap_events = SwapEvent.query.filter(
        SwapEvent.status.in_(['pending', 'active'])
    ).count()

    # Get all users
    users = User.query.all()
    
    # Get active borrows
    active_borrows = BorrowedAccessory.query.filter(
        BorrowedAccessory.status.in_(['approved', 'delivered'])
    ).count()
    
    # Create stats dictionary
    stats = {
        'total_users': User.query.count(),
        'pending_items': len(pending_items),
        'approved_items': len(approved_items),
        'active_borrows': active_borrows
    }
    
    return render_template('admin_dashboard.html', 
                         pending_items=pending_items, 
                         rejected_items=rejected_items,
                         approved_items=approved_items,
                         pending_swap_items=pending_swap_items,
                         active_swap_events=active_swap_events,
                         users=users,
                         stats=stats)

@app.route('/approve/<int:item_id>')
@login_required
def approve(item_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    pending_item = PendingAccessory.query.get_or_404(item_id)
    user = User.query.get(pending_item.user_id)
    if pending_item.type == 'donate':
        # Create new accessory for donation (same as lend items)
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
        db.session.add(accessory)
        db.session.delete(pending_item)
        db.session.commit()
        flash('Donation approved! The user will be notified.', 'success')
        # Send Gmail notification to user
        if user and user.email:
            donation_url = url_for('donations', _external=True)
            subject = f"Your Donation '{pending_item.name}' was Approved"
            body = (
                f"<p><b>Thank you for your generosity! 🙏</b></p>"
                f"<p>We're happy to let you know that your donation — <b>{pending_item.name}</b> — has been "
                f"<span style='color:green;'><b>approved</b></span> by our admin team. 🎉</p>"
                f"<p>Your thoughtful contribution helps strengthen our culture of sharing and support. "
                f"Every item given brings value to someone in need, and we're grateful to have you as part of this mission.</p>"
                f"<p><b>Our team at Antlers will contact you shortly</b> to coordinate the pickup of the donated item. "
                f"Please ensure it's ready and accessible at the agreed time. 🛻</p>"
                f"<p>You can also track and manage your donations in your dashboard under <b>My Donations</b>.</p>"
                f"<p>"
                f"<a href='{donation_url}' style='display:inline-block;padding:10px 20px;"
                f"background:#4CAF50;color:white;text-decoration:none;border-radius:5px;'>"
                f"View My Donations</a></p>"
                f"<p>If the button doesn't work, simply copy and paste this link into your browser:<br>"
                f"<a href='{donation_url}'>{donation_url}</a></p>"
                f"<p>With sincere thanks,<br><b>Team Antlers</b></p>"
            )
            send_notification_email(user.email, subject, body)
        return redirect(url_for('admin_dashboard'))
    else:
        # Create new accessory for lending
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
    user = User.query.get(pending_item.user_id)
    if request.method == 'POST':
        rejection_reason = request.form.get('rejection_reason', '').strip()
        if not rejection_reason:
            flash('Please provide a reason for rejection', 'danger')
            return redirect(url_for('admin_dashboard'))
        # Create rejected accessory entry
        # Handle the case where datetime might be None (especially for donations)
        item_datetime = pending_item.datetime if pending_item.datetime else func.now()
        
        # Handle the case where residence might be None (especially for donations)
        item_residence = pending_item.residence if pending_item.residence else "Not specified"
        
        rejected_item = RejectedAccessory(
            name=pending_item.name,
            category=pending_item.category,
            image=pending_item.image,
            location=pending_item.location,
            residence=item_residence,
            datetime=item_datetime,
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
            # Send Gmail notification to user if donation
            if pending_item.type == 'donate' and user and user.email:
                donation_url = url_for('donations', _external=True)
                subject = f"Your Donation '{pending_item.name}' was Rejected"
                body = (
                    f"<p>We appreciate your willingness to donate <b>{pending_item.name}</b>, but unfortunately it was <span style='color:red;'><b>rejected</b></span> by the admin.</p>"
                    f"<p><b>Reason:</b> {rejection_reason}</p>"
                    f"<p>You can track your donations and see the reason for rejection in your dashboard under <b>My Donations</b>.</p>"
                    f"<p><a href='{donation_url}' style='display:inline-block;padding:10px 20px;background:#4CAF50;color:white;text-decoration:none;border-radius:5px;'>View My Donations</a></p>"
                    f"<p>If the button doesn't work, copy and paste this link into your browser:<br>"
                    f"<a href='{donation_url}'>{donation_url}</a></p>"
                    f"<p>Thank you for your spirit of giving. Please consider donating again in the future!</p>"
                    f"<p>Warm regards,<br><b>The Team</b></p>"
                )
                send_notification_email(user.email, subject, body)
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error rejecting item {item_id}: {str(e)}")
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
                description=request.form['description'],  # Make it required
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
        from datetime import datetime
        datetime_str = request.form.get('datetime')
        pickup_datetime = None
        if datetime_str:
            try:
                pickup_datetime = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('Invalid date and time format.', 'error')
                return redirect(url_for('donate'))
        pending_item = PendingAccessory(
            name=request.form['name'],
            description=request.form['description'],  # Make it required
            image=image,
            type='donate',
            category=request.form['category'],
            location=request.form['location'],
            datetime=pickup_datetime,
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
        # Email lender about new borrow request
        lender = User.query.get(item.user_id)
        if lender and lender.email:
            subject = f"New Borrow Request for {item.name}"
            # Generate absolute URL for borrow requests page
            borrow_requests_url = url_for('borrow_requests', _external=True)
            body = (
    f"<p>Hello there,</p>"

    f"<p>You've received a new <b>borrow request</b> from <b>{current_user.username}</b> "
    f"for your item: <b>{item.name}</b>.</p>"

    f"<p>Someone out there values your item — that's how community sharing grows stronger! 🌱</p>"

    f"<p>Please review the request and respond at your convenience:</p>"

    f"<p>"
    f"<a href='{borrow_requests_url}' style='display:inline-block;padding:10px 20px;"
    f"background:#4CAF50;color:white;text-decoration:none;border-radius:5px;'>"
    f"View Borrow Requests</a></p>"

    f"<p>If the button doesn't work, simply copy and paste this link into your browser:<br>"
    f"<a href='{borrow_requests_url}'>{borrow_requests_url}</a></p>"

    f"<p>Thank you for being a part of something bigger. Your generosity makes a difference. 🙌</p>"

    f"<p>Warm regards,<br><b>The Team</b></p>"
)

            send_notification_email(lender.email, subject, body)
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
    pending_requests = BorrowedAccessory.query.filter(
        BorrowedAccessory.lender_id == current_user.id,
        BorrowedAccessory.status == 'pending'
    ).all()
    
    # Get approved and delivered requests for items owned by the user
    active_requests = BorrowedAccessory.query.filter(
        BorrowedAccessory.lender_id == current_user.id,
        BorrowedAccessory.status.in_(['approved', 'delivered'])
    ).all()
    
    return render_template('borrow_requests.html',
                         pending_requests=pending_requests,
                         active_requests=active_requests)

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
        system_message = f"Borrow request for {accessory.name} has been approved by {current_user.username}. You can use this chat to coordinate the handover. Say Helloooouu!!"
        
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
        # Email borrower about approval
        borrower = User.query.get(borrowed_item.borrower_id)
        if borrower and borrower.email:
            subject = f"Your Borrow Request for {accessory.name} was Approved"
            # Generate link to confirm delivery (for borrower)
            confirm_delivery_url = url_for('confirm_borrower_delivery', borrow_id=borrowed_item.id, _external=True)
            body = (
                f"<p>Great news!</p>"
                f"<p>Your borrow request for <b>{accessory.name}</b> has been <span style='color:green;'><b>approved</b></span> by "
                f"<b>{current_user.username}</b>. 🎉</p>"
                f"<p>You can now coordinate the handover directly through the chat system.</p>"
                f"<p><i>Tip:</i> Be polite, punctual, and take good care of the item — our community thrives on trust and respect. 🤝</p>"
                f"<p>Head over to your chat panel and get in touch!</p>"
                f"<hr>"
                f"<p><b>Important:</b> After you receive the item, <b>don't forget to return to the portal and confirm delivery</b> to complete the process.</p>"
                f"<p>Click here to confirm delivery: "
                f"<a href='{confirm_delivery_url}' style='display:inline-block;padding:10px 20px;background:#4CAF50;color:white;text-decoration:none;border-radius:5px;'>Confirm Delivery</a></p>"
                f"<p>If the button doesn't work, copy and paste this link into your browser:<br>"
                f"<a href='{confirm_delivery_url}'>{confirm_delivery_url}</a></p>"
                f"<p>All the best,<br><b>The Team</b></p>"
            )
            send_notification_email(borrower.email, subject, body)
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
        # Email borrower about rejection
        borrower = User.query.get(rejected_request.borrower_id)
        accessory = Accessory.query.get(borrowed_item.accessory_id)
        if borrower and borrower.email:
            subject = f"Your Borrow Request for {accessory.name if accessory else 'an item'} was Rejected"
            body = f"""
            <p>
            Hello there,
            </p>

            <p>
            Unfortunately, your borrow request was rejected by <b>{current_user.username}</b>.
            </p>

            <p>
            <b style="color: red;">Reason:</b> {rejection_reason}
            </p>

            <hr>

            <p>
            But hey, don't let this discourage you. Every setback is a setup for a stronger comeback. 💪
            </p>

            <p>
            Your willingness to participate already shows initiative — that's something many people never take.
            </p>

            <p>
            Take a moment to reflect, improve where needed, and try again. We believe in second chances — and in <b>you</b>.
            </p>

            <p>
            Keep pushing forward — your contribution truly matters and makes a difference.
            </p>

            <p>
            Best regards,<br>
            <b>The Team</b>
            </p>
            """

            send_notification_email(borrower.email, subject, body)
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
    
    # Check if a return request already exists for this item and borrower (not just rejected)
    existing_active_return = ReturnedAccessory.query.filter(
        ReturnedAccessory.accessory_id == borrowed_item.accessory_id,
        ReturnedAccessory.borrower_id == current_user.id,
        ReturnedAccessory.status.in_(['pending', 'approved'])
    ).first()
    if existing_active_return:
        flash('You have already submitted a return request for this item. Please wait for it to be processed.', 'warning')
        return redirect(url_for('user_dashboard'))
    
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
            # Email lender about updated return request
            lender = User.query.get(existing_return.lender_id)
            if lender and lender.email:
                subject = f"Return Request Updated for {existing_return.item_name}"
                body = f"<p>The return request for <b>{existing_return.item_name}</b> was updated by <b>{current_user.username}</b> and is waiting for your approval.</p>"
                send_notification_email(lender.email, subject, body)
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
            # Email lender about new return request
            lender = User.query.get(return_request.lender_id)
            if lender and lender.email:
                subject = f"New Return Request for {return_request.item_name}"
                approve_return_url = url_for('approve_return', return_id=return_request.id, _external=True)
                body = f"""
                <p>
                Hello there,
                </p>
                <p>
                You've received a new <b>return request</b> for the item: <b>{return_request.item_name}</b>.
                </p>
                <p>
                Requested by: <b>{current_user.username}</b>
                </p>
                <hr>
                <p>
                Please take a moment to review the request and take appropriate action.<br>
                <a href='{approve_return_url}' style='display:inline-block;padding:10px 20px;background:#4CAF50;color:white;text-decoration:none;border-radius:5px;'>Approve Return</a>
                </p>
                <p>If the button doesn't work, copy and paste this link into your browser:<br>
                <a href='{approve_return_url}'>{approve_return_url}</a></p>
                <p>
                Your timely response helps us maintain trust and a smooth experience across the platform.
                </p>
                <p>
                Thank you for being a responsible and valued member of our community! 🌟
                </p>
                <p>
                Best regards,<br>
                <b>The Team</b>
                </p>
                """
                send_notification_email(lender.email, subject, body)
        
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
        # Email borrower about approval
        borrower = User.query.get(return_request.borrower_id)
        if borrower and borrower.email:
            subject = f"Your Return Request for {return_request.item_name} was Approved"
            # Generate chat and confirm delivery URLs
            chat_url = url_for('chat', borrow_id=borrowed_accessory.id, _external=True) if borrowed_accessory else url_for('chat_history', _external=True)
            confirm_delivery_url = url_for('return_requests', _external=True)
            body = (
                f"<p>Good news!</p>"
                f"<p>Your return request for <b>{return_request.item_name}</b> has been <span style='color:green;'><b>approved</b></span> "
                f"by <b>{current_user.username}</b>.</p>"
                f"<p>Please use the <b>chat</b> to coordinate a convenient time and place to complete the return. 💬<br>"
                f"<a href='{chat_url}' style='display:inline-block;padding:10px 20px;background:#2196F3;color:white;text-decoration:none;border-radius:5px;'>Open Chat</a></p>"
                f"<p>Once the item has been handed over, don't forget to <b>confirm the delivery</b> in your dashboard — "
                f"this helps maintain trust and transparency within our community. ✅<br>"
                f"<a href='{confirm_delivery_url}' style='display:inline-block;padding:10px 20px;background:#4CAF50;color:white;text-decoration:none;border-radius:5px;'>Confirm Delivery</a></p>"
                f"<p>Thanks for being responsible and contributing to a smooth sharing experience. 🙌</p>"
                f"<p>Warm regards,<br><b>The Team</b></p>"
            )
            send_notification_email(borrower.email, subject, body)
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
        # Email borrower about rejection
        borrower = User.query.get(return_request.borrower_id)
        accessory = Accessory.query.get(borrowed_accessory.accessory_id)
        if borrower and borrower.email:
            subject = f"Your Return Request for {accessory.name if accessory else 'an item'} was Rejected"
            body = f"<p>Your return request for <b>{accessory.name}</b> was rejected by <b>{current_user.username}</b>.<br>Reason: {rejection_reason}</p>"
            send_notification_email(borrower.email, subject, body)
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while rejecting the request.', 'danger')
        print(f"Error details: {str(e)}")
    
    # Redirect to chat with the borrower instead of dashboard
    return redirect(url_for('chat', borrow_id=borrowed_accessory.id, show_modal=1))

@app.route('/lender_dashboard')
@login_required
def lender_dashboard():
    return redirect(url_for('user_dashboard'))

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
    if borrow_request.lender_id != current_user.id:
        flash('You are not authorized to confirm this delivery', 'danger')
        return redirect(url_for('user_dashboard'))
    if borrow_request.status != 'approved':
        flash('You can only confirm delivery for approved requests', 'warning')
        return redirect(url_for('user_dashboard'))
    borrow_request.lender_confirmed_delivery = True
    if borrow_request.borrower_confirmed_delivery:
        borrow_request.status = 'delivered'
        flash('Delivery completed! Both parties have confirmed the handover.', 'success')
    else:
        flash('You have confirmed the item handover. Waiting for borrower confirmation.', 'success')
    db.session.commit()
    return redirect(url_for('user_dashboard'))

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

@app.route('/chat/<int:borrow_id>', methods=['GET', 'POST'])
@login_required
def chat(borrow_id):
    borrow_request = BorrowedAccessory.query.get_or_404(borrow_id)
    if request.method == 'POST':
        message = request.form.get('message')
        if message:
            chat_message = ChatMessage(
                borrow_id=borrow_id,
                sender_id=current_user.id,
                recipient_id=borrow_request.lender_id if current_user.id == borrow_request.borrower_id else borrow_request.borrower_id,
                message=message
            )
            db.session.add(chat_message)
            db.session.commit()
            flash('Message sent!', 'success')
            # Email recipient about new chat message
            recipient = User.query.get(chat_message.recipient_id)
            if recipient and recipient.email:
                subject = f"New Chat Message from {current_user.username}"
                body = (
    f"<p>Hello there,</p>"
    f"<p>You've received a new chat message from <b>{current_user.username}</b> "
    f"regarding <b>{borrow_request.accessory.name if borrow_request.accessory else 'an item'}</b>.</p>"
    f"<p><i>Here's what they said:</i></p>"
    f"<blockquote style='margin:10px 0;padding:10px;border-left:4px solid #4CAF50;"
    f"background:#f9f9f9;font-style:italic;'>{message}</blockquote>"
    f"<p>Please check your dashboard or chat panel to reply.</p>"
    f"<p>Your prompt response helps keep conversations smooth and meaningful. 🗨️</p>"
    f"<p>Warm regards,<br><b>The Team</b></p>"
)
                send_notification_email(recipient.email, subject, body)
            return redirect(url_for('chat', borrow_id=borrow_id))
    # For GET requests, render the chat page with messages
    chat_messages = ChatMessage.query.filter_by(borrow_id=borrow_id).order_by(ChatMessage.timestamp.asc()).all()
    
    # Add date variables for template
    from datetime import date
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    return render_template('chat.html', borrow_request=borrow_request, chat_messages=chat_messages, today=today, yesterday=yesterday)

def send_notification_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = os.getenv('GMAIL_USER')
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(os.getenv('GMAIL_USER'), os.getenv('GMAIL_PASS'))
        server.sendmail(os.getenv('GMAIL_USER'), to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f'Failed to send notification email: {e}')
        return False

@app.route('/admin/swap-items')
@login_required
def admin_swap_items():
    if current_user.role != 'admin':
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('home'))
    pending_items = SwapItem.query.filter_by(status='pending').all()
    approved_items = SwapItem.query.filter_by(status='approved').all()
    rejected_items = SwapItem.query.filter_by(status='rejected').all()
    swap_events = SwapEvent.query.all()
    return render_template(
        'admin_swap_items.html',
                         pending_items=pending_items,
                         approved_items=approved_items,
                         rejected_items=rejected_items,
        swap_events=swap_events
    )

@app.route('/admin/swap-assignments')
@login_required
def admin_swap_assignments():
    if current_user.role != 'admin':
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('home'))
    # Get the current (active or pending) swap event
    current_event = SwapEvent.query.filter(SwapEvent.status.in_(['pending', 'active'])).order_by(SwapEvent.start_date.desc()).first()
    swap_items = []
    if current_event:
        swap_items = current_event.items
    return render_template(
        'admin_swap_assignments.html',
        current_event=current_event,
        swap_items=swap_items
    )

@app.route('/admin/manual-assign-item', methods=['POST'])
@login_required
def manual_assign_item():
    if current_user.role != 'admin':
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('home'))
    item_id = request.form.get('item_id')
    recipient_id = request.form.get('recipient_id')
    if not item_id or not recipient_id:
        flash('Missing item or recipient.', 'danger')
        return redirect(url_for('admin_swap_assignments'))
    item = SwapItem.query.get(item_id)
    recipient = User.query.get(recipient_id)
    if not item or not recipient:
        flash('Invalid item or recipient.', 'danger')
        return redirect(url_for('admin_swap_assignments'))
    item.recipient_id = recipient.id
    item.status = 'approved'  # or whatever status is appropriate
    db.session.commit()
    flash(f'Item {item.name} assigned to {recipient.username}.', 'success')
    return redirect(url_for('admin_swap_assignments'))

@app.route('/admin/start-swap-event/<int:event_id>', methods=['POST'])
@login_required
def start_swap_event(event_id):
    """Start a swap event"""
    if current_user.role != 'admin':
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('admin_swap_items'))
    
    try:
        swap_event = SwapEvent.query.get_or_404(event_id)
        
        if swap_event.status != 'pending':
            flash('Only pending events can be started.', 'danger')
            return redirect(url_for('admin_swap_items'))
        
        if len(swap_event.items) < 2:
            flash('At least 2 items are required to start an event.', 'danger')
            return redirect(url_for('admin_swap_items'))
        
        swap_event.status = 'active'
        db.session.commit()
        
        flash(f'Swap event "{swap_event.name}" has been started successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error starting swap event {event_id}: {str(e)}")
        flash('An error occurred while starting the event.', 'danger')
    
    return redirect(url_for('admin_swap_items'))

@app.route('/admin/complete-swap-event/<int:event_id>', methods=['POST'])
@login_required
def complete_swap_event(event_id):
    """Complete a swap event"""
    if current_user.role != 'admin':
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('admin_swap_items'))
    
    try:
        swap_event = SwapEvent.query.get_or_404(event_id)
        
        if swap_event.status != 'active':
            flash('Only active events can be completed.', 'danger')
            return redirect(url_for('admin_swap_items'))
        
        swap_event.status = 'completed'
        db.session.commit()
        
        flash(f'Swap event "{swap_event.name}" has been completed successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error completing swap event {event_id}: {str(e)}")
        flash('An error occurred while completing the event.', 'danger')
    
    return redirect(url_for('admin_swap_items'))

@app.route('/admin/approve-swap-item/<int:item_id>', methods=['POST'])
@login_required
def approve_swap_item(item_id):
    """Approve a swap item"""
    if current_user.role != 'admin':
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('admin_swap_items'))
    
    try:
        swap_item = SwapItem.query.get_or_404(item_id)
        
        if swap_item.status != 'pending':
            flash('Only pending items can be approved.', 'danger')
            return redirect(url_for('admin_swap_items'))
        
        swap_item.status = 'approved'
        db.session.commit()
        
        flash(f'Swap item "{swap_item.name}" has been approved successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error approving swap item {item_id}: {str(e)}")
        flash('An error occurred while approving the item.', 'danger')
    
    return redirect(url_for('admin_swap_items'))

@app.route('/admin/reject-swap-item/<int:item_id>', methods=['POST'])
@login_required
def reject_swap_item(item_id):
    """Reject a swap item"""
    if current_user.role != 'admin':
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('admin_swap_items'))
    
    try:
        swap_item = SwapItem.query.get_or_404(item_id)
        rejection_reason = request.form.get('rejection_reason')
        
        if not rejection_reason:
            flash('Please provide a rejection reason.', 'danger')
            return redirect(url_for('admin_swap_items'))
        
        if swap_item.status != 'pending':
            flash('Only pending items can be rejected.', 'danger')
            return redirect(url_for('admin_swap_items'))
        
        swap_item.status = 'rejected'
        swap_item.rejection_reason = rejection_reason
        db.session.commit()
        
        flash(f'Swap item "{swap_item.name}" has been rejected.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error rejecting swap item {item_id}: {str(e)}")
        flash('An error occurred while rejecting the item.', 'danger')
    
    return redirect(url_for('admin_swap_items'))

@app.route('/secret')
@login_required
def secret():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    
    users = User.query.all()
    return render_template('secret.html' , navi=users)

@app.route('/donations')
@login_required
def donations():
    # Approved donations: items in Accessory with type 'donate' and user_id = current_user.id
    approved_donations = Accessory.query.filter_by(user_id=current_user.id, type='donate').all()
    # Rejected donations: items in RejectedAccessory with type 'donate' and user_id = current_user.id
    rejected_donations = RejectedAccessory.query.filter_by(user_id=current_user.id, type='donate').all()
    return render_template('donation.html', approved_donations=approved_donations, rejected_donations=rejected_donations)

# After all models and db/app initialization, but before route definitions
with app.app_context():
    create_tables_and_admin()

if __name__ == '__main__':
    app.run(debug=True)