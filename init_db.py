from app import app, db, create_tables_and_admin

if __name__ == '__main__':
    with app.app_context():
        print("Creating database tables...")
        create_tables_and_admin()
        print("Database initialized successfully!")
        print("Admin user created with username: 'admin' and password: 'antlers@admin2003'") 