from flask import Flask, request, render_template, redirect, url_for, flash, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from twilio.rest import Client
import vonage
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# ---------------------- Configuration ----------------------
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'inventory.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Mail
app.config['MAIL_SERVER'] = 'sandbox.smtp.mailtrap.io'
app.config['MAIL_PORT'] = 2525
app.config['MAIL_USERNAME'] = os.getenv('MAILTRAP_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAILTRAP_PASSWORD')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID = 'AC4eeb47a822315401f64ea9516eca1dff'
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_FROM = 'whatsapp:+14155238886'
YOUR_WHATSAPP_TO = 'whatsapp:+2348068004048'
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Vonage (SMS)
VONAGE_API_KEY = '9df9e28e'
VONAGE_API_SECRET = 'KXev1JDTrRxeUh6g'
VONAGE_FROM = 'Vonage'
MY_PHONE = '2348068004048'

# ---------------------- Models ----------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(128), nullable=False)
    business_name = db.Column(db.String(150), nullable=False)
    
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)  

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def is_active_user(self):
        return self.is_active


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    initial_quantity = db.Column(db.Integer, nullable=False)
    threshold = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    alert_sent = db.Column(db.Boolean, default=False)

    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"<Product {self.name}>"


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    customer_name = db.Column(db.String(150))
    sold_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch_id = db.Column(db.String(100))

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_info = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ItemIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity_added = db.Column(db.Integer, nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class ItemOut(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity_removed = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    removed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    removed_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------------- Auth ----------------------
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    if not getattr(g, '_login_message_flashed', False):
        flash("Please log in to access this page.", "warning")
        g._login_message_flashed = True
    return redirect(url_for("login"))

@app.route("/admin/users")
@login_required
def manage_users():
    if not current_user.is_admin:
        flash("Unauthorized access", "danger")
        return redirect(url_for("home"))
    
    users = User.query.all()
    return render_template("admin_users.html", users=users, business_name=current_user.business_name)


@app.route("/admin/toggle_user/<int:user_id>", methods=["POST"])
@login_required
def toggle_user_status(user_id):
    if not current_user.is_admin:
        flash("Unauthorized", "danger")
        return redirect(url_for("home"))

    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash("Cannot deactivate another admin.", "danger")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        status = "activated" if user.is_active else "deactivated"
        flash(f"User {user.username} has been {status}.", "success")
    return redirect(url_for("manage_users"))

@app.route("/toggle_user/<int:user_id>")
@login_required
def toggle_user(user_id):
    if not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for("home"))
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    flash(f"{user.username}'s account is now {'active' if user.is_active else 'inactive'}.", "info")
    return redirect(url_for("admin_dashboard"))

# ---------------------- Notification Functions ----------------------
def send_low_stock_sms(product_name, current_stock):
    client = vonage.Client(key=VONAGE_API_KEY, secret=VONAGE_API_SECRET)
    sms = vonage.Sms(client)
    sms.send_message({
        "from": VONAGE_FROM,
        "to": MY_PHONE,
        "text": f"Low stock alert: {product_name} has only {current_stock} left."
    })

def send_low_stock_email(product_name, current_stock):
    msg = Message(
        subject="Low Stock Alert",
        sender=app.config['MAIL_USERNAME'],
        recipients=["test@example.com"],
        body=f"Product: {product_name}\nStock: {current_stock}"
    )
    mail.send(msg)

def send_low_stock_whatsapp(product_name, current_stock):
    try:
        twilio_client.messages.create(
            body=f"Low stock: {product_name} - {current_stock} units left.",
            from_=TWILIO_WHATSAPP_FROM,
            to=YOUR_WHATSAPP_TO
        )
    except Exception as e:
        print("WhatsApp error:", e)

# ---------------------- Routes ----------------------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        user = User(
            username=request.form["username"],
            email=request.form["email"],
            business_name=request.form["business_name"]
        )
        user.set_password(request.form["password"])
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("home"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and user.check_password(request.form["password"]):
            login_user(user)
            return redirect(url_for("home"))
        flash("Invalid login", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for('home'))

    user_count = User.query.count()
    product_count = Product.query.count()
    total_sales = db.session.query(db.func.sum(Sale.total_price)).scalar() or 0

    return render_template(
        'admin_dashboard.html',
        user_count=user_count,
        product_count=product_count,
        total_sales=round(total_sales, 2)
    )


@app.route("/admin/home")
@login_required
def admin_home():
    if not current_user.is_admin:
        flash("Access denied", "danger")
        return redirect(url_for("home"))
    return render_template("admin_home.html")

@app.route("/add_product", methods=["POST"])
@login_required
def add_product():
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    threshold = int(request.form["threshold"])
    price = float(request.form["price"])

    new_product = Product(
        name=name,
        initial_quantity=quantity,
        threshold=threshold,
        price=price,
        user_id=current_user.id 
    )

    db.session.add(new_product)
    db.session.commit()

    flash(f"Product '{name}' added successfully!", "success")
    return redirect(url_for("home"))


@app.route("/edit_product/<int:product_id>")
@login_required
def edit_product(product_id):
    p = Product.query.get_or_404(product_id)
    return render_template("edit_product.html", product=p)

@app.route("/update_product/<int:product_id>", methods=["POST"])
@login_required
def update_product(product_id):
    p = Product.query.get_or_404(product_id)
    p.name = request.form["name"]
    p.initial_quantity = int(request.form["quantity"])
    p.threshold = int(request.form["threshold"])
    db.session.commit()
    flash("Product updated.", "info")
    return redirect(url_for("home"))

@app.route("/delete_product/<int:product_id>", methods=["POST"])
@login_required
def delete_product(product_id):
    p = Product.query.get_or_404(product_id)
    db.session.delete(p)
    db.session.commit()
    flash("Product deleted.", "danger")
    return redirect(url_for("home"))

@app.route("/restock/<int:product_id>", methods=["POST"])
@login_required
def restock_product(product_id):
    p = Product.query.get_or_404(product_id)
    p.initial_quantity += int(request.form["restock_quantity"])
    db.session.commit()
    return redirect(url_for("home"))

@app.route("/record_sales", methods=["GET", "POST"])
@login_required
def record_sales():
    if current_user.is_admin:
        products = Product.query.order_by(Product.created_at.desc()).all()
    else:
        products = Product.query.filter_by(user_id=current_user.id).order_by(Product.created_at.desc()).all()

    if request.method == "POST":
        customer_name = request.form.get("customer_name")
        batch_id = datetime.now().strftime("BATCH-%Y%m%d%H%M%S")
        sales_made = False 

        for product in products:
            qty_key = f"quantity_{product.id}"
            quantity = request.form.get(qty_key)

            if quantity and int(quantity) > 0:
                quantity = int(quantity)
                unit_price = product.price
                total_price = quantity * unit_price

                sale = Sale(
                    product_id=product.id,
                    quantity_sold=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                    customer_name=customer_name,
                    batch_id=batch_id
                )

                db.session.add(sale)
                sales_made = True  

                # Stock checking logic...
                total_sold = db.session.query(db.func.sum(Sale.quantity_sold)).filter_by(product_id=product.id).scalar() or 0
                current_stock = product.initial_quantity - total_sold
                if current_stock <= product.threshold and not product.alert_sent:
                    send_low_stock_email(product.name, current_stock)
                    send_low_stock_sms(product.name, current_stock)
                    send_low_stock_whatsapp(product.name, current_stock)
                    product.alert_sent = True
                elif current_stock > product.threshold:
                    product.alert_sent = False

        if sales_made:
            db.session.commit()
            return redirect(url_for("receipt_batch", batch_id=batch_id))
        else:
            flash("No products were selected for sale.", "warning")
            return redirect(url_for("record_sales"))

    return render_template("record_sales.html", products=products)

@app.route("/sales_history")
@login_required
def sales_history():
    # Get optional filters from query parameters
    customer_query = request.args.get("customer", "").strip().lower()
    date_query = request.args.get("date", "")

    # Base query for current user's sales
    sales_query = Sale.query.order_by(Sale.sold_at.desc())

    # Apply filters if present
    if customer_query:
        sales_query = sales_query.filter(Sale.customer_name.ilike(f"%{customer_query}%"))
    if date_query:
        try:
            date_obj = datetime.strptime(date_query, "%Y-%m-%d").date()
            sales_query = sales_query.filter(db.func.date(Sale.sold_at) == date_obj)
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")

    # Fetch all matching sales and group by batch_id
    sales = sales_query.all()
    grouped = {}

    for sale in sales:
        if sale.batch_id not in grouped:
            grouped[sale.batch_id] = {
                "batch_id": sale.batch_id,
                "timestamp": sale.sold_at,
                "customer_name": sale.customer_name,
            }

    # Convert to list for rendering
    batches = list(grouped.values())

    return render_template(
        "sales_history.html",
        batches=batches,
        business_name=current_user.business_name
    )

@app.route("/receipt/batch/<batch_id>")
@login_required
def receipt_batch(batch_id):
    sales = Sale.query.filter_by(batch_id=batch_id).all()
    sale_details = []
    total_amount = 0

    for sale in sales:
        product = Product.query.get(sale.product_id)
        total_amount += sale.total_price  # Accumulate the total

        sale_details.append({
            'product_name': product.name,
            'quantity': sale.quantity_sold,
            'unit_price': sale.unit_price,
            'total_price': sale.total_price,
            'timestamp': sale.sold_at,
            'customer_name': sale.customer_name
        })

    return render_template(
        "receipt_batch.html",
        sales=sale_details,
        batch_id=batch_id,
        business_name=current_user.business_name,
        total_amount=total_amount
    )
with app.app_context():
    db.create_all()

@app.route('/admin/backup-restore')
@login_required
def backup_restore():
    if not current_user.is_admin:
        flash("Access denied", "danger")
        return redirect(url_for('home'))
    return render_template('admin_backup_restore.html')  # Create this HTML file

@app.route("/admin/items")
@login_required
def manage_items():
    if not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for("home"))

    items = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin_items.html", items=items)

@app.route("/admin/suppliers", methods=["GET", "POST"])
@login_required
def manage_suppliers():
    if not current_user.is_admin:
        flash("Access denied", "danger")
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form["name"]
        contact_info = request.form.get("contact_info")

        new_supplier = Supplier(name=name, contact_info=contact_info)
        db.session.add(new_supplier)
        db.session.commit()
        flash("Supplier added successfully!", "success")
        return redirect(url_for("manage_suppliers"))

    suppliers = Supplier.query.order_by(Supplier.created_at.desc()).all()
    return render_template("admin_suppliers.html", suppliers=suppliers)



@app.route("/admin/item-in", methods=["GET", "POST"])
@login_required
def item_in():
    if not current_user.is_admin:
        flash("Access denied", "danger")
        return redirect(url_for("home"))

    products = Product.query.order_by(Product.created_at.desc()).all()

    if request.method == "POST":
        product_id = int(request.form["product_id"])
        quantity = int(request.form["quantity"])

        product = Product.query.get_or_404(product_id)
        product.initial_quantity += quantity

        # Save ItemIn record
        item_in_record = ItemIn(
            product_id=product.id,
            quantity_added=quantity,
            added_by=current_user.id
        )

        db.session.add(item_in_record)
        db.session.commit()

        flash(f"Restocked {quantity} units for '{product.name}'", "success")
        return redirect(url_for("item_in"))

    item_in_records = ItemIn.query.order_by(ItemIn.added_at.desc()).limit(20).all()

    return render_template("admin_item_in.html", products=products, item_in_records=item_in_records)

@app.route("/admin/item-out", methods=["GET", "POST"])
@login_required
def item_out():
    if not current_user.is_admin:
        flash("Access denied", "danger")
        return redirect(url_for("home"))

    products = Product.query.order_by(Product.created_at.desc()).all()

    if request.method == "POST":
        product_id = int(request.form["product_id"])
        quantity = int(request.form["quantity"])
        reason = request.form["reason"].strip()

        product = Product.query.get_or_404(product_id)

        # Ensure there's enough stock
        total_sold = db.session.query(db.func.sum(Sale.quantity_sold)).filter_by(product_id=product.id).scalar() or 0
        current_stock = product.initial_quantity - total_sold

        if quantity > current_stock:
            flash("Not enough stock to remove that quantity.", "danger")
            return redirect(url_for("item_out"))

        product.initial_quantity -= quantity

        item_out_record = ItemOut(
            product_id=product.id,
            quantity_removed=quantity,
            reason=reason,
            removed_by=current_user.id
        )

        db.session.add(item_out_record)
        db.session.commit()

        flash(f"Removed {quantity} from '{product.name}' for reason: {reason}", "success")
        return redirect(url_for("item_out"))

    item_out_records = ItemOut.query.order_by(ItemOut.removed_at.desc()).limit(20).all()

    return render_template("admin_item_out.html", products=products, item_out_records=item_out_records)


@app.route("/debug")
def debug():
    return f"DB path: {app.config['SQLALCHEMY_DATABASE_URI']}"

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)