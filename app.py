from flask import Flask, request, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from twilio.rest import Client
import vonage, requests
from datetime import datetime
import os

app = Flask(__name__)

# Flask mail config 
app.config['MAIL_SERVER'] = 'sandbox.smtp.mailtrap.io'
app.config['MAIL_PORT'] = 2525
app.config['MAIL_USERNAME'] = '72b00c7ea509b9'
app.config['MAIL_PASSWORD'] = '4d530cfedcc473'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

mail = Mail(app)

app.secret_key = 'your_secret_key_here'


VONAGE_API_KEY = '9df9e28e'
VONAGE_API_SECRET = 'KXev1JDTrRxeUh6g'
MY_PHONE = '2348068004048' 
VONAGE_FROM = 'Vonage' 

def send_low_stock_sms(product_name, current_stock):
    client = vonage.Client(key=VONAGE_API_KEY, secret=VONAGE_API_SECRET)
    sms = vonage.Sms(client)

    responseData = sms.send_message({
        "from": VONAGE_FROM,
        "to": MY_PHONE,
        "text": f"Low stock alert: '{product_name}' has only {current_stock} left!",
    })

    if responseData["messages"][0]["status"] == "0":
        print(" Vonage SMS sent successfully.")
    else:
        print(f" SMS failed: {responseData['messages'][0]['error-text']}")


def send_low_stock_email(product_name, current_stock):
    print(f"Sending EMAIL: {product_name} is low. Stock: {current_stock}")
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = Message(
        subject=f" Low Stock Alert ({timestamp})",
        sender=app.config['MAIL_USERNAME'],
        recipients=["test@example.com"],
        body=(
            f"Low Stock Alert \n\n"
            f"Product: {product_name}\n"
            f"Current Stock: {current_stock}\n"
            f"Time: {timestamp}\n\n"
            f"Please restock soon."
        )
    )
    mail.send(msg)

# setting up whatsapp notification
TWILIO_ACCOUNT_SID = 'AC4eeb47a822315401f64ea9516eca1dff'
TWILIO_AUTH_TOKEN = os.getenv('317aa7ab901f3a18b8ad09e911ec698b')
TWILIO_WHATSAPP_FROM = 'whatsapp:+14155238886'  
YOUR_WHATSAPP_TO = 'whatsapp:+2348068004048'

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_low_stock_whatsapp(product_name, current_stock):
    try:
        message = client.messages.create(
            body=f" Low stock alert: '{product_name}' is now at {current_stock} units. Restock soon.",
            from_=TWILIO_WHATSAPP_FROM,
            to=YOUR_WHATSAPP_TO
        )
        print("WhatsApp message sent:", message.sid)
    except Exception as e:
        print(" WhatsApp failed:", e)


# Database setup
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'inventory.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Product model
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    initial_quantity = db.Column(db.Integer, nullable=False)
    threshold = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    alert_sent = db.Column(db.Boolean, default=False)


    def __repr__(self):
        return f'<Product {self.name}>'
#sale    
class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False)
    sold_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    

#record_sale
@app.route("/record_sale", methods=["POST"])
def record_sale():
    product_id = int(request.form["product_id"])
    quantity_sold = int(request.form["quantity_sold"])
    
    sale = Sale(product_id=product_id, quantity_sold=quantity_sold)
    db.session.add(sale)
    db.session.commit()
    
    
    # Recalculate stock
    product = Product.query.get(product_id)
    total_sold = db.session.query(db.func.sum(Sale.quantity_sold)).filter_by(product_id=product.id).scalar() or 0
    current_stock = product.initial_quantity - total_sold

    print(f"DEBUG: {product.name} stock = {current_stock}, threshold = {product.threshold}, alert_sent = {product.alert_sent}")

    # Trigger alert if stock is below threshold and alert hasn't been sent yet
    if current_stock <= product.threshold and not product.alert_sent:
        send_low_stock_email(product.name, current_stock)
        send_low_stock_sms(product.name, current_stock)
        send_low_stock_whatsapp(product.name, current_stock) 
        product.alert_sent = True
        db.session.commit()


    # Reset alert if restocked
    if current_stock > product.threshold and product.alert_sent:
        product.alert_sent = False
        db.session.commit()

    flash(" Sale recorded successfully!", "info")
    return redirect(url_for("home"))


# Home route
#@app.route("/", methods=["GET"])
#def home():
    all_products = Product.query.order_by(Product.created_at.desc()).all()
    product_data = []

    for product in all_products:
        total_sold = db.session.query(db.func.sum(Sale.quantity_sold)).filter_by(product_id=product.id).scalar() or 0
        current_stock = product.initial_quantity - total_sold
        is_low = current_stock <= product.threshold

        product_data.append({
            "id": product.id,
            "name": product.name,
            "current_stock": current_stock,
            "threshold": product.threshold,
            "created_at": product.created_at,
            "low_stock": is_low
        })

    return render_template("home.html", products=product_data)

@app.route("/")
def home():
    products = Product.query.order_by(Product.created_at.desc()).all()

    for p in products:
        p.total_sold = db.session.query(db.func.sum(Sale.quantity_sold)).filter_by(product_id=p.id).scalar() or 0

    return render_template("home.html", products=products)


#restock route
@app.route("/restock/<int:product_id>", methods=["POST"])
def restock_product(product_id):
    added_qty = int(request.form["restock_quantity"])
    product = Product.query.get(product_id)
    
    if product:
        product.initial_quantity += added_qty

        # Reset alert if stock goes above threshold
        total_sold = db.session.query(db.func.sum(Sale.quantity_sold)).filter_by(product_id=product.id).scalar() or 0
        current_stock = product.initial_quantity - total_sold
        if current_stock > product.threshold:
            product.alert_sent = False

        db.session.commit()
        flash(f" '{product.name}' restocked by {added_qty} units.", "success")
    
    return redirect(url_for("home"))
 


# add_product
@app.route("/add_product", methods=["POST"])
def add_product():
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    threshold = int(request.form["threshold"])

    new_product = Product(name=name, initial_quantity=quantity, threshold=threshold)
    db.session.add(new_product)
    db.session.commit()

    flash(f" Product '{name}' added successfully!", "success")
    return redirect(url_for("home"))

#edit form
@app.route("/edit_product/<int:product_id>")
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("edit_product.html", product=product)

#handle update
@app.route("/update_product/<int:product_id>", methods=["POST"])
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.name = request.form["name"]
    product.initial_quantity = int(request.form["quantity"])
    product.threshold = int(request.form["threshold"])
    db.session.commit()
    flash(f" '{product.name}' updated successfully.", "success")
    return redirect(url_for("home"))

#delete product
@app.route("/delete_product/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash(f"🗑 Product '{product.name}' deleted.", "danger")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)

