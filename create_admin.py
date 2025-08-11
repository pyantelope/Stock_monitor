from main import app, db, User

with app.app_context():
    if not User.query.filter_by(email="admin@example.com").first():
        admin = User(
            username="admin",
            email="admin@example.com",
            business_name="Everkel Ventures"
        )
        admin.set_password("adminpass123")  
        db.session.add(admin)
        db.session.commit()
        print(" Admin user created.")
    else:
        print(" Admin already exists.")