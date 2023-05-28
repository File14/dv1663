from flask import Flask, render_template, request
from flask.globals import g
import mysql.connector # pip install mysql-connector-python
from datetime import datetime, timedelta

app = Flask(__name__)

# MySQL Login Details
app.config['DATABASE'] = {
    'host': 'localhost',
    'user': 'root',
    'password': 'password',
    'database': 'dv1663'
}

# The current maximum guests that the resturant can serve at the same time
MAXIMUM_GUESTS = 50

# SQLite connection functions
def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(**app.config['DATABASE'])
    return g.db

# Create database tables
def create_tables():
    with app.app_context():
        db = get_db()
        c = db.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                ssn VARCHAR(16) NOT NULL UNIQUE,
                name VARCHAR(32) NOT NULL,
                email VARCHAR(32) NOT NULL,
                phone VARCHAR(32) NOT NULL
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(32) NOT NULL UNIQUE,
                description VARCHAR(256) NOT NULL,
                price INT NOT NULL
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                customer_id INT NOT NULL,
                date TIMESTAMP NOT NULL,
                guests INT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                meal_id INT NOT NULL,
                quantity INT NOT NULL,
                special_requests VARCHAR(64),
                date TIMESTAMP NOT NULL,
                cooked BOOLEAN NOT NULL DEFAULT 0,
                reservation_id INT NOT NULL,
                FOREIGN KEY (meal_id) REFERENCES meals(id),
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        ''')

        db.commit()

# The default meals
MEALS = [
    ('Harvest Bowl', 'A nourishing blend of quinoa, roasted seasonal vegetables, and a creamy tahini dressing.', 100),
    ('Green Goddess Wrap', 'A delightful combination of fresh greens, avocado, cucumber, and sprouts, wrapped in a whole wheat tortilla with a zesty herb dressing.', 130),
    ('Mediterranean Falafel Plate', 'Crispy falafel served with a colorful array of hummus, tabbouleh, and grilled pita bread.', 120),
    ('Thai Coconut Curry', 'A fragrant and spicy curry featuring tofu, mixed vegetables, and aromatic herbs, served with steamed jasmine rice.', 140),
    ('Rainbow Salad', 'A vibrant salad bursting with color and flavor, featuring a mix of crisp lettuce, cherry tomatoes, bell peppers, shredded carrots, and a tangy citrus vinaigrette.', 90),
    ('Lentil Shepherds Pie', 'A comforting vegan twist on a classic dish, made with savory lentils, mashed potatoes, and a medley of seasonal vegetables.', 100),
    ('Mushroom Risotto', 'Creamy Arborio rice cooked to perfection with a medley of sautéed mushrooms, aromatic herbs, and vegetable broth.', 130),
    ('Spicy Black Bean Burger', 'A hearty and flavorful vegan burger made with a homemade black bean patty, topped with avocado, lettuce, tomato, and chipotle mayo, served with sweet potato fries.', 120),
    ('Vegan Pad Thai', 'Traditional Thai stir-fried rice noodles with tofu, bean sprouts, scallions, crushed peanuts, and a tangy tamarind sauce.', 140),
    ('Mediterranean Quinoa Salad', 'A refreshing salad featuring fluffy quinoa, juicy cherry tomatoes, cucumber, kalamata olives, fresh herbs, and a lemon-herb dressing.', 100)
]

def insert_meals():
    with app.app_context():
            db = get_db()
            c = db.cursor()

            # Insert the default meals and we skip the existing entries
            for meal in MEALS:
                name, description, price = meal
                c.execute('INSERT IGNORE INTO meals (name, description, price) VALUES (%s, %s, %s)', (name, description, price))

            db.commit()

def create_procedures():
    with app.app_context():
        db = get_db()
        c = db.cursor()

        c.execute('DROP PROCEDURE IF EXISTS GetOrderStatusCount')

        c.execute('''CREATE PROCEDURE GetOrderStatusCount(out current_orders INT, out cooked_orders INT)
        BEGIN
            DECLARE today_start TIMESTAMP;
            DECLARE today_end TIMESTAMP;
            SET today_start = TIMESTAMP(DATE(CURRENT_TIMESTAMP));
            SET today_end = TIMESTAMP(DATE_ADD(DATE(CURRENT_TIMESTAMP), INTERVAL 1 DAY));

            -- Get the count of current orders
            SELECT COUNT(*) INTO current_orders
            FROM orders
            WHERE date >= today_start AND date < today_end;

            -- Get the count of cooked orders
            SELECT COUNT(*) INTO cooked_orders
            FROM orders
            WHERE date >= today_start AND date < today_end AND cooked = 1;
        END;''')
        db.commit()

def create_functions():
    with app.app_context():
        db = get_db()
        c = db.cursor()

        c.execute('DROP FUNCTION IF EXISTS CalculateTotalPrice;')

        c.execute('''
        CREATE FUNCTION CalculateTotalPrice(res_id INT) RETURNS INT
            BEGIN
                DECLARE total INT DEFAULT 0;
                DECLARE current_meal_id INT;
                DECLARE current_quantity INT;
                DECLARE meal_price INT DEFAULT 0;
                DECLARE cur CURSOR FOR SELECT meal_id, quantity FROM orders WHERE reservation_id = res_id;
                DECLARE CONTINUE HANDLER FOR NOT FOUND SET @done = TRUE;

                OPEN cur;
                fetch_loop: LOOP
                    FETCH cur INTO current_meal_id, current_quantity;

                    IF @done THEN
                        LEAVE fetch_loop;
                    END IF;

                    SELECT price INTO meal_price FROM meals WHERE id = current_meal_id;
                   
                    SET total = total + (meal_price * current_quantity);
                END LOOP;

                CLOSE cur;

                RETURN total;
            END
        ''')
        db.commit()

def check_availability(request):
    date = request.form['reservation-date']
    time = request.form['reservation-time']
    guests = int(request.form['guests'])

    start = datetime.strptime(date + ' ' + time, '%Y-%m-%d %H:%M')
    end = start + timedelta(hours=2)

    # Check if the requested time is at least 2 hours from the current time
    current_time = datetime.now().replace(second=0, microsecond=0)
    if start - current_time < timedelta(hours=2):
        return False, date, time, 'Sorry, but you must book at least 2 hours in advance.'

    db = get_db()
    c = db.cursor()

    # Check if the maximum guest count is reached for the requested time
    c.execute('SELECT SUM(guests) FROM reservations WHERE date >= %s AND date < %s', (start, end))
    total_guests = c.fetchone()[0]

    if total_guests is None:
        total_guests = 0

    # Calculate the remaining available seats
    remaining_seats = MAXIMUM_GUESTS - total_guests

    if remaining_seats >= guests:
        return True, date, time, 'This date and time is available! Please fill in the details on the right side.'
    else:
        return False, date, time, f'Sorry, but we do not fit {guests} guests at {time}. There are currently {remaining_seats} spots left.'

# Home page
@app.route('/')
def home():
    with app.app_context():
        db = get_db()
        c = db.cursor()

        # Show the current meals
        c.execute('SELECT * FROM meals')
        meals = c.fetchall()
        return render_template('index.html', meals=meals)

# Reservation page
@app.route('/reservation', methods=['GET', 'POST'])
def reservation():
    with app.app_context():
        if request.method == 'POST':
            if 'check-availability-btn' in request.form:
                possible, date, time, message = check_availability(request)                
                return render_template('reservation.html', current_date=date, current_time=time, availability_message=message)
            elif 'make-reservation-btn' in request.form:
                ssn = request.form['ssn']
                name = request.form['name']
                email = request.form['email']
                phone = request.form['phone']
                guests = request.form['guests']
                
                possible, date, time, message = check_availability(request)
                
                if possible:
                    db = get_db()
                    c = db.cursor()
                    # Get the customer ID based on the provided SSN
                    c.execute('SELECT id FROM customers WHERE ssn = %s', (ssn,))
                    customer_id = c.fetchone()

                    # Check if customer exists
                    if customer_id is None:
                        # Insert the customer information
                        c.execute('''INSERT INTO customers (ssn, name, email, phone) VALUES (%s, %s, %s, %s)''', (ssn, name, email, phone))
                        customer_id = c.lastrowid
                    else:
                        # Extract the customer ID from the fetched result
                        customer_id = customer_id[0]

                    # Convert the date string to a datetime.date object
                    reservation_date = datetime.strptime(date, '%Y-%m-%d').date()
                    # Convert the time string to a time object
                    reservation_time = datetime.strptime(time, '%H:%M').time()
                    # Combine the date and time to create a timestamp
                    reservation_datetime = datetime.combine(reservation_date, reservation_time)

                    # Insert the reservation with the customer ID
                    c.execute('''INSERT INTO reservations (customer_id, date, guests) VALUES (%s, %s, %s)''', (customer_id, reservation_datetime, guests))
                    db.commit()

                    message = f'{name}, a reservation was made for {guests} guests on {date} at {time}. A confirmation mail has been sent to you.'
    
                return render_template('reservation.html', current_date=date, current_time=time, reservation_message=message)

        # Default page
        date = datetime.now() + timedelta(hours=2)
        current_date = date.strftime('%Y-%m-%d')
        current_time = date.strftime('%H:%M')
        return render_template('reservation.html', current_date=current_date, current_time=current_time)

# Staff page
@app.route('/staff')
def staff():
    with app.app_context():
        db = get_db()
        c = db.cursor()

        # Call the stored procedure
        c.execute('CALL GetOrderStatusCount(@current_orders, @cooked_orders)')
        c.execute('SELECT @current_orders, @cooked_orders')
        result = c.fetchone()
        current_orders = result[0]
        cooked_orders = result[1]

        return render_template('staff.html', current_orders=current_orders, cooked_orders=cooked_orders)

# Waiter/waitress page
@app.route('/waiter', methods=['GET', 'POST'])
def waiter():
    with app.app_context():
        db = get_db()
        c = db.cursor()

        # Get the current valid reservations
        current_datetime = datetime.now()
        offsetDate = current_datetime - timedelta(hours=2)

        c.execute('''
                SELECT reservations.id, reservations.date, reservations.guests, customers.name AS customer_name FROM reservations
                INNER JOIN customers ON reservations.customer_id = customers.id
                WHERE reservations.date >= %s
                ORDER BY reservations.date DESC''', (offsetDate,))
        
        reservations = c.fetchall()

        if request.method == 'POST':
            if 'check-price-btn' in request.form:
                reservation_id = request.form['reservation_id']

                # Call the stored function
                c.execute('SELECT CalculateTotalPrice(%s)', (reservation_id,))
                total_price = c.fetchone()[0]
                price_message = f'{total_price} kr'

                return render_template('waiter.html', id=int(reservation_id), price_message=price_message, reservations=reservations)
            elif 'add-order-btn' in request.form:
                reservation_id = request.form['reservation_id']
                meal_id = request.form['meal_id']
                quantity = request.form['quantity']
                special_requests = request.form['special_requests']
                current_datetime = datetime.now()

                db = get_db()
                c = db.cursor()

                # Check if the meal exists
                c.execute('SELECT COUNT(*) FROM meals WHERE id = %s', (meal_id,))
                meal_exists = c.fetchone()[0] > 0

                # Check if the reservation ID exists
                c.execute('SELECT COUNT(*) FROM reservations WHERE id = %s', (reservation_id,))
                reservation_exists = c.fetchone()[0] > 0

                if meal_exists and reservation_exists:
                    # Insert the order into the database
                    c.execute('''INSERT INTO orders (meal_id, quantity, special_requests, date, reservation_id) VALUES (%s, %s, %s, %s, %s)''',
                            (meal_id, quantity, special_requests, current_datetime, reservation_id))
                    db.commit()
                    message = f'The order was created for reservation id {reservation_id}.'
                else:
                    message = 'Invalid meal or reservation ID.'

                return render_template('waiter.html', reservations=reservations, order_message=message)
        return render_template('waiter.html', reservations=reservations)

# Kitchen page
@app.route('/kitchen', methods=['GET', 'POST'])
def kitchen():
    if request.method == 'POST':
        order_id = request.form['order_id']

        db = get_db()
        c = db.cursor()

        # Update the cooked status of the order
        c.execute('UPDATE orders SET cooked = 1 WHERE id = %s', (order_id,))
        db.commit()

    db = get_db()
    c = db.cursor()

    # Retrieve the orders that are not cooked
    c.execute('''
        SELECT orders.id, orders.reservation_id, meals.name AS meal_name, orders.quantity, orders.special_requests, customers.name AS customer_name FROM orders
        INNER JOIN reservations ON orders.reservation_id = reservations.id
        INNER JOIN customers ON reservations.customer_id = customers.id
        INNER JOIN meals ON orders.meal_id = meals.id
        WHERE orders.cooked = 0
        ORDER BY orders.id ASC
    ''')
    orders = c.fetchall()

    return render_template('kitchen.html', orders=orders)

if __name__ == '__main__':
    create_tables()
    insert_meals();
    create_procedures();
    create_functions();
    app.run(debug=True)
