from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
admin = Admin(app)
db = SQLAlchemy(app)

class PendingAccessory(db.Model):
    # ... (existing code)

class RejectedAccessory(db.Model):
    # ... (existing code)

@app.route('/reject/<int:item_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def reject(item_id):
    item = PendingAccessory.query.get_or_404(item_id)
    
    if request.method == 'POST':
        rejection_reason = request.form.get('rejection_reason', '').strip()
        if not rejection_reason:
            flash('Please provide a reason for rejection', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        # Create rejected accessory entry
        rejected_item = RejectedAccessory(
            name=item.name,
            category=item.category,
            image=item.image,
            location=item.location,
            residence=item.residence,
            delivery_preference=item.delivery_preference,
            datetime=item.datetime,
            description=item.description,
            type=item.type,
            user_id=item.user_id,
            rejection_reason=rejection_reason
        )
        
        try:
            db.session.add(rejected_item)
            db.session.delete(item)
            db.session.commit()
            flash('Item has been rejected and moved to rejected items.', 'warning')
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while rejecting the item.', 'danger')
            
        return redirect(url_for('admin_dashboard'))
    
    return render_template('reject_item.html', item=item) 