from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
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
    role = db.Column(db.String(50), default='user')
    created_at = db.Column(db.DateTime, default=func.now())
    
    # Relationships with explicit foreign keys
    approved_items = db.relationship('Accessory', 
                                   foreign_keys='Accessory.user_id',
                                   backref=db.backref('owner', lazy=True))
    
    borrowed_items = db.relationship('BorrowedAccessory',
                                   foreign_keys='BorrowedAccessory.borrower_id',
                                   backref=db.backref('borrower', lazy=True))
    
    lent_items = db.relationship('BorrowedAccessory',
                                foreign_keys='BorrowedAccessory.lender_id',
                                backref=db.backref('lender', lazy=True))

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
    status = db.Column(db.String(50))  # 'pending', 'approved', 'rejected', 'returned'
    pickup_location = db.Column(db.String(150))
    pickup_datetime = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=func.now())
    
    # Relationship with Accessory
    accessory = db.relationship('Accessory', backref='borrow_requests')

class ReturnedAccessory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    accessory_id = db.Column(db.Integer, db.ForeignKey('accessory.id'))
    borrower_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    lender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=func.now())
    return_location = db.Column(db.String(150))
    pickup_location = db.Column(db.String(150))
    return_datetime = db.Column(db.String(100))
    return_notes = db.Column(db.String(200))
    item_name = db.Column(db.String(100))
    
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

# Function to create tables and the admin user
def create_tables_and_admin():
    db.create_all()  # Creates tables if they don't exist
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='antlers@admin2003', role='admin')
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def home():
    # Only show items that are available
    items = Accessory.query.filter_by(is_available=True).all()
    return render_template('home.html', items=items)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        user = User(username=username, password=password, role='user')
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
    
    # Get items borrowed by the user with their relationships
    borrowed_items = BorrowedAccessory.query.filter_by(borrower_id=current_user.id).options(
        db.joinedload(BorrowedAccessory.lender),
        db.joinedload(BorrowedAccessory.accessory)
    ).all()
    
    # Get borrow requests for items owned by the user
    borrow_requests = BorrowedAccessory.query.join(Accessory).filter(
        Accessory.user_id == current_user.id,
        BorrowedAccessory.status == 'pending'
    ).all()
    
    return render_template('user_dashboard.html', 
                         my_approved_items=my_approved_items,
                         my_pending_items=my_pending_items,
                         borrowed_items=borrowed_items,
                         borrow_requests=borrow_requests)

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

@app.route('/reject/<int:item_id>')
@login_required
def reject(item_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('home'))
    pending_item = PendingAccessory.query.get_or_404(item_id)
    db.session.delete(pending_item)
    db.session.commit()
    flash('Item rejected successfully', 'success')
    return redirect(url_for('admin_dashboard'))

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
                datetime=pickup_datetime,  # Use the converted datetime object
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
        if not request.form.get('pickup_location') or not request.form.get('pickup_datetime'):
            flash('Please fill in all required fields', 'error')
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
            status='pending'
        )
        db.session.add(borrowed_item)
        db.session.commit()
        flash('Borrow request submitted successfully', 'success')
        return redirect(url_for('user_dashboard'))
    
    return render_template('borrow_details.html', item=item)

@app.route('/borrow_requests')
@login_required
def borrow_requests():
    # Get pending requests for items owned by the user
    pending_requests = BorrowedAccessory.query.join(Accessory).filter(
        Accessory.user_id == current_user.id,
        BorrowedAccessory.status == 'pending'
    ).all()
    
    # Get approved requests for items owned by the user
    approved_requests = BorrowedAccessory.query.filter_by(
        lender_id=current_user.id,
        status='approved'
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
        accessory.is_available = False
        
        # Commit all changes
        db.session.commit()
        
        flash('Borrow request approved successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the request.', 'danger')
        print(f"Error details: {str(e)}")
    
    return redirect(url_for('borrow_requests'))

@app.route('/reject_borrow/<int:borrow_id>', methods=['POST'])
@login_required
def reject_borrow(borrow_id):
    borrowed_item = BorrowedAccessory.query.get_or_404(borrow_id)
    if borrowed_item.lender_id != current_user.id:
        flash('You are not authorized to reject this request', 'error')
        return redirect(url_for('borrow_requests'))
    
    # Delete the rejected borrow request
    db.session.delete(borrowed_item)
    db.session.commit()
    flash('Borrow request rejected and removed', 'success')
    return redirect(url_for('borrow_requests'))

@app.route('/return_request/<int:borrow_id>')
@login_required
def return_request(borrow_id):
    borrowed_item = BorrowedAccessory.query.filter_by(
        id=borrow_id,
        borrower_id=current_user.id,
        status='approved'
    ).first_or_404()
    
    return render_template('return_request.html', borrowed_item=borrowed_item)

@app.route('/return_item/<int:item_id>', methods=['POST'])
@login_required
def return_item(item_id):
    # Get the borrowed item
    borrowed_item = BorrowedAccessory.query.filter_by(
        id=item_id,
        borrower_id=current_user.id,
        status='approved'
    ).first_or_404()
    
    # Get the accessory to store its name
    accessory = Accessory.query.get(borrowed_item.accessory_id)
    
    # Create a new return request
    return_request = ReturnedAccessory(
        accessory_id=borrowed_item.accessory_id,
        borrower_id=current_user.id,
        lender_id=borrowed_item.lender_id,
        status='pending',
        return_location=request.form.get('return_location'),
        pickup_location=request.form.get('pickup_location'),
        return_datetime=datetime.strptime(request.form.get('return_datetime'), '%Y-%m-%dT%H:%M'),
        return_notes=request.form.get('return_notes'),
        item_name=accessory.name if accessory else borrowed_item.item_name
    )
    
    db.session.add(return_request)
    db.session.commit()
    
    flash('Return request submitted successfully. Waiting for lender approval.', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/approve_return/<int:return_id>', methods=['POST'])
@login_required
def approve_return(return_id):
    return_request = ReturnedAccessory.query.get_or_404(return_id)
    if return_request.lender_id != current_user.id:
        flash('You are not authorized to approve this return', 'error')
        return redirect(url_for('return_requests'))
    
    try:
        # Get the borrow request and accessory
        borrow_request = BorrowedAccessory.query.filter_by(
            accessory_id=return_request.accessory_id,
            borrower_id=return_request.borrower_id,
            status='approved'
        ).first()
        
        accessory = Accessory.query.get(return_request.accessory_id)
        
        if borrow_request and accessory:
            # Create history entry
            history = BorrowHistory(
                item_name=accessory.name,
                item_category=accessory.category,
                borrower_id=borrow_request.borrower_id,
                lender_id=borrow_request.lender_id,
                borrow_date=borrow_request.created_at,
                return_date=func.now(),
                pickup_location=borrow_request.pickup_location,
                return_location=return_request.return_location
            )
            
            # Add to history
            db.session.add(history)
            
            # Delete the borrow request
            db.session.delete(borrow_request)
            
            # Update return request status and make accessory available again
            return_request.status = 'approved'
            accessory.is_available = True
            
            db.session.commit()
            flash('Return approved successfully', 'success')
        else:
            flash('Borrow request or accessory not found', 'error')
            
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while approving the return', 'danger')
        print(f"Error: {str(e)}")
    
    return redirect(url_for('return_requests'))

@app.route('/reject_return/<int:return_id>', methods=['POST'])
@login_required
def reject_return(return_id):
    return_request = ReturnedAccessory.query.get_or_404(return_id)
    if return_request.lender_id != current_user.id:
        flash('You are not authorized to reject this return', 'error')
        return redirect(url_for('return_requests'))
    
    return_request.status = 'rejected'
    db.session.commit()
    flash('Return rejected', 'success')
    return redirect(url_for('return_requests'))

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
    
    return render_template('return_requests.html',
                         pending_returns=pending_returns_as_lender + pending_returns_as_borrower,
                         approved_returns=approved_returns_as_lender + approved_returns_as_borrower,
                         is_lender=True)  # Add this flag to differentiate between lender and borrower views

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

if __name__ == '__main__':
    with app.app_context():
        create_tables_and_admin()
    app.run()
