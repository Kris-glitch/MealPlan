from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from flask_bootstrap import Bootstrap
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from logging.config import dictConfig
from itertools import zip_longest
import random
import pdfkit


# Configure logging
dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'DEBUG',
        'handlers': ['wsgi']
    }
})

# Configure application
app = Flask(__name__)
Bootstrap(app)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///meals.db")

def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            flash("You must provide a username!")
            return render_template("login.html")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("You must provide a password!")
            return render_template("login.html")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid username and/or password")
            return render_template("login.html")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        app.logger.info('User %s with id %d logged in successfully', request.form.get("username"), rows[0]["id"])

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    app.logger.info('User %s logging out', session["user_id"])
    session.clear()

    # Redirect user to login form
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # If method is POST
    if request.method == "POST":
        name = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Personal touch - Require users’ passwords to have some number of letters, numbers, and/or symbols
        password_symbols = ['!', '#', '$', '%', '.', '_', '&']

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("You must provide a username!")
            return render_template("register.html")

        # Ensure password was submitted
        if not request.form.get("password"):
            flash("You must provide a password!")
            return render_template("register.html")

        # Ensure confirmation was submitted
        if not confirmation:
            flash("You must confirm the password!")
            return render_template("register.html")

        # Require users’ passwords to be 8 char long and to have some number of letters, numbers, and/or symbols
        if len(password) < 8:
            flash("Password must be at least 8 characters long!")
            return render_template("register.html")

        if not any(char.isdigit() for char in password):
            flash("Password must have at least one number!")
            return render_template("register.html")

        if not any(char.isupper() for char in password):
            flash("Password must have at least one uppercase!")
            return render_template("register.html")

        if not any(char in password_symbols for char in password):
            flash("must contain at least one symbol of following: ! # $ % . _ &")
            return render_template("register.html")

        # Check if password and confirmation match
        if not password == confirmation:
            flash("Password doesn't match")
            return render_template("register.html")

        # Check if username is taken
        rows = db.execute("SELECT username FROM users WHERE username = ?", name)
        if len(rows) > 0:
            flash("Username is taken")
            return redirect("/register")

        # Add the new user into the database
        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES(?,?)", name, hash)

        # Remember which user has logged in
        rows = db.execute("SELECT id FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash('Registered!')
        return redirect("/myrecipes")

    # If method is GET
    else:
        return render_template("register.html")

@app.route("/myrecipes", methods=["GET", "POST"])
@login_required
def myrecipes():
    user_id = session["user_id"]
    app.logger.debug('/myrecipes called, request method %s, user id %d', request.method, user_id)

    # If method is post
    if request.method == "POST":
        # Retrieve form data and update the database
        name = request.form.get("recipe")
        ingredients = request.form.getlist("ingredientInputItem")
        quantities = request.form.getlist("quantityInputItem")
        measurements = request.form.getlist("measurementInputItem")
        description = request.form.get("description")
        category = request.form.get("category")

        # Check for mistakes
        if not name:
            flash("You must provide name")
            return render_template("myrecipes.html")

        name_exists = db.execute("SELECT 1 FROM recipes WHERE name=:name and user_id=:user_id", user_id=user_id, name=name)

        if name_exists:
            flash("You must provide a unique name")
            return render_template("myrecipes.html")
        if not ingredients:
            flash("You must provide ingredients")
            return render_template("myrecipes.html")
        if not quantities:
            flash("You must provide quantities")
            return render_template("myrecipes.html")
        if not description:
            flash("You must provide a description")
            return render_template("myrecipes.html")
        elif category=="Categories":
            flash("You must choose a category")
            return render_template("myrecipes.html")
        else:
            # If no mistakes insert recipes and ingredients into the data base
            ACTIVE_DAY = 0
            app.logger.debug('Adding new recipe with name %s, description %s and category %s', name, description, category)
            db.execute("INSERT INTO recipes (user_id, name, description, category, active_day) VALUES (?, ?, ?, ?, ?)", user_id, name, description, category, ACTIVE_DAY)
            id_recipe = db.execute("SELECT id FROM recipes WHERE user_id=:user_id AND name=:name", user_id=user_id, name=name)[0]['id']

            for ingredient, quantity, measurement in zip(ingredients, quantities, measurements):
                if ingredient and quantity and measurement:
                    app.logger.debug('Adding new ingredient to recipe with ID %d of type %s and amount %s', id_recipe, ingredient, quantity)
                    db.execute("INSERT INTO ingredients (user_id, ingredient, quantity, measurement, id_recipe) VALUES (?, ?, ?, ?, ?)", user_id, ingredient, quantity, measurement, id_recipe)

    # If method is GET or the above is done set recipes in category and zip to print on table
    formatted_recipes = []

    breakfast_recipes = db.execute("SELECT name FROM recipes WHERE category='Breakfast' AND user_id=:user_id", user_id=user_id)
    lunch_recipes = db.execute("SELECT name FROM recipes WHERE category='Lunch' AND user_id=:user_id", user_id=user_id)
    dinner_recipes = db.execute("SELECT name FROM recipes WHERE category='Dinner' AND user_id=:user_id", user_id=user_id)
    dessert_recipes = db.execute("SELECT name FROM recipes WHERE category='Dessert' AND user_id=:user_id", user_id=user_id)

    for breakfast, lunch, dinner, dessert in zip_longest(breakfast_recipes, lunch_recipes, dinner_recipes, dessert_recipes):
        formatted_recipes.append({'breakfast':breakfast, 'lunch':lunch, 'dinner':dinner, 'dessert':dessert})

    # Render the template of the same page
    return render_template('myrecipes.html', recipes=formatted_recipes)

@app.route("/card", methods=["GET", "POST"])
@login_required
def card():
    user_id = session["user_id"]
    app.logger.debug('/card called, request method %s, user id %d', request.method, user_id)

    if request.method == "GET":

        # Get the name value that was clicked
        name = request.args.get('name')
        app.logger.debug('The name of the recipe is %s', name)
        # PR: ASSERT that name was provided
        if not name:
            flash("Wrong URL, URL should state: /card?name=recipename")
            return redirect("/myrecipes")

        # PR: ASSERT that the recipe exists
        name_exists = db.execute("SELECT 1 FROM recipes WHERE name=:name and user_id=:user_id", user_id=user_id, name=name)

        if not name_exists:
            flash("The recipe name doesn't exist. Wrong URL, URL should state: /card?name=recipename ")
            return redirect("/myrecipes")

        # Get the description of the recipe by that name
        recipe = db.execute("SELECT id, description FROM recipes WHERE user_id=:user_id AND name=:name", user_id=user_id, name=name)

        description = recipe[0]['description']
        id_recipe = recipe[0]['id']

        app.logger.debug('The description of the recipe is %s and the id is %d', description, id_recipe)

        # Get the ingredients list, the quantities list and the measuremnts of the recipe by that name
        ingredients= db.execute("SELECT ingredient FROM ingredients WHERE user_id=:user_id AND id_recipe=:id_recipe", user_id=user_id, id_recipe=id_recipe)
        quantities = db.execute("SELECT quantity FROM ingredients WHERE user_id=:user_id AND id_recipe=:id_recipe", user_id=user_id, id_recipe=id_recipe)
        measurements = db.execute("SELECT measurement FROM ingredients WHERE user_id=:user_id AND id_recipe=:id_recipe", user_id=user_id, id_recipe=id_recipe)


        formated_ingredients = []

        for ingredient, quantity, measurement in zip(ingredients, quantities, measurements):
            formated_ingredients.append({'ingredient':ingredient, 'quantity':quantity, 'measurement':measurement})


        return render_template("card.html", formated_ingredients=formated_ingredients, name=name, description=description)

    # If method is post
    else:
        # Get the old name
        app.logger.debug('/card called, request method %s, user id %d', request.method, user_id)
        name = request.form.get("hiddenField")

        # Get the old description of the recipe by that name
        recipe = db.execute("SELECT id, description FROM recipes WHERE user_id=:user_id AND name=:name", user_id=user_id, name=name)
        description = recipe[0]['description']
        id_recipe = recipe[0]['id']

        app.logger.debug('The description of the recipe is %s and the id is %d', description, id_recipe)

        # Get the old ingredients and quantities
        ingredients= db.execute("SELECT ingredient FROM ingredients WHERE user_id=:user_id AND id_recipe=:id_recipe", user_id=user_id, id_recipe=id_recipe)
        quantities = db.execute("SELECT quantity FROM ingredients WHERE user_id=:user_id AND id_recipe=:id_recipe", user_id=user_id, id_recipe=id_recipe)
        measurements = db.execute("SELECT measurement FROM ingredients WHERE user_id=:user_id AND id_recipe=:id_recipe", user_id=user_id, id_recipe=id_recipe)

        # Get the new name
        new_name = request.form['new_name']

        # Get the new description
        new_description = request.form['new_description']

        # Get the new ingredients and quantities
        new_ingredients = request.form.getlist('new_ingredients')
        new_quantities = request.form.getlist('new_quantities')

        # Check for mistakes

        name_exists = db.execute("SELECT 1 FROM recipes WHERE name=:name and user_id=:user_id", user_id=user_id, name=new_name)

        if not new_name:
            new_name=name
            app.logger.debug('new name is %s ', new_name)

        if not name==new_name:
            not_equal = True
        else:
            not_equal = False

        if not_equal==True and name_exists:
            flash("You must provide a unique name")
            return redirect(f"/card?name={name}")

        if not new_description:
            new_description=description
            app.logger.debug('new description is %s', new_description)

        if not new_ingredients:
            app.logger.debug('new ingredients is empty')
            new_ingredients=ingredients
        if not new_quantities:
            new_quantities=quantities


        app.logger.debug('Updating recipe name to %s ', new_name)
        db.execute("UPDATE recipes SET name=:name WHERE id=:id AND user_id=:user_id", name=new_name, id=id_recipe, user_id=user_id)

        app.logger.debug('Updating recipe description to %s ', new_description)
        db.execute("UPDATE recipes SET description=:description WHERE user_id=:user_id AND id=:id", description=new_description, user_id=user_id, id=id_recipe)

        db.execute("DELETE FROM ingredients WHERE user_id=:user_id AND id_recipe=:id_recipe", user_id=user_id, id_recipe=id_recipe)

        for new_ingredient, new_quantity in zip(new_ingredients, new_quantities):
            app.logger.debug('Updating ingredient to recipe with ID %d of type %s and amount %s', id_recipe, new_ingredient, new_quantity)
            db.execute("INSERT INTO ingredients (user_id, id_recipe, ingredient, quantity) VALUES (?, ?, ?, ?)",
                        user_id, id_recipe, new_ingredient, new_quantity)

        new_formated_ingredients = []
        for new_ingredient, new_quantity in zip(new_ingredients, new_quantities):
            new_formated_ingredients.append({'ingredient':new_ingredient, 'quantity':new_quantity})

        return render_template("card.html", formated_ingredients=new_formated_ingredients, name=new_name, description=new_description)

@app.route("/")
@login_required
def homepage():
    user_id = session["user_id"]
    days_of_week = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

    row_count = db.execute("SELECT COUNT(*) FROM weekly")[0]['COUNT(*)']

    if row_count > 0:
        breakfast_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Breakfast' AND user_id=:user_id", user_id=user_id)
        lunch_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Lunch' AND user_id=:user_id", user_id=user_id)
        dinner_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Dinner' AND user_id=:user_id", user_id=user_id)
        dessert_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Dessert' AND user_id=:user_id", user_id=user_id)
        return render_template("homepage.html", days_of_week=days_of_week, breakfast_weekly=breakfast_weekly, lunch_weekly=lunch_weekly, dinner_weekly=dinner_weekly, dessert_weekly=dessert_weekly)


    return render_template("homepage.html")

@app.route("/generate", methods=["POST"])
@login_required
def generate():
    user_id = session["user_id"]
    app.logger.debug('/card called, request method %s, user id %d', request.method, user_id)

    breakfast_recipes = db.execute("SELECT id, name, active_day, category, user_id FROM recipes WHERE category='Breakfast' AND user_id=:user_id", user_id=user_id)
    lunch_recipes = db.execute("SELECT id, name, active_day, category, user_id FROM recipes WHERE category='Lunch' AND user_id=:user_id", user_id=user_id)
    dinner_recipes = db.execute("SELECT id, name, active_day, category, user_id FROM recipes WHERE category='Dinner' AND user_id=:user_id", user_id=user_id)
    dessert_recipes = db.execute("SELECT id, name, active_day, category, user_id FROM recipes WHERE category='Dessert' AND user_id=:user_id", user_id=user_id)

    days_of_week = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

    breakfast_weekly = []
    lunch_weekly = []
    dinner_weekly = []
    dessert_weekly = []

    row_count = db.execute("SELECT COUNT(*) FROM weekly")[0]['COUNT(*)']

    if not row_count == 0:
        db.execute("DELETE FROM weekly WHERE user_id=:user_id",user_id=user_id)

    for recipe in breakfast_recipes:
        recipe['active_day'] = random.randint(1, 7)

    sorted_breakfast = sorted(breakfast_recipes, key=lambda x: x['active_day'])

    for recipe in lunch_recipes:
        recipe['active_day'] = random.randint(1, 7)

    sorted_lunch = sorted(lunch_recipes, key=lambda x: x['active_day'])

    for recipe in dinner_recipes:
        recipe['active_day'] = random.randint(1, 7)

    sorted_dinner = sorted(dinner_recipes, key=lambda x: x['active_day'])

    for recipe in dinner_recipes:
        recipe['active_day'] = random.randint(1, 7)

    sorted_dessert = sorted(dessert_recipes, key=lambda x: x['active_day'])


    for i in range(7):
        if i < len(sorted_breakfast):
            breakfast_weekly.append(sorted_breakfast[i])
        if i < len(sorted_lunch):
            lunch_weekly.append(sorted_lunch[i])
        if i < len(sorted_dinner):
            dinner_weekly.append(sorted_dinner[i])
        if i < len(sorted_dessert):
            dessert_weekly.append(sorted_dessert[i])

    sql = "INSERT INTO weekly (name, id, category, active_day, user_id) VALUES (?, ?, ?, ?, ?)"

    for recipe in breakfast_weekly:
        db.execute(sql, recipe['name'], recipe['id'], recipe['category'], recipe['active_day'], recipe['user_id'])

    for recipe in lunch_weekly:
        db.execute(sql, recipe['name'], recipe['id'], recipe['category'], recipe['active_day'], recipe['user_id'])

    for recipe in dinner_weekly:
        db.execute(sql, recipe['name'], recipe['id'], recipe['category'], recipe['active_day'], recipe['user_id'])

    for recipe in dessert_weekly:
        db.execute(sql, recipe['name'], recipe['id'], recipe['category'], recipe['active_day'], recipe['user_id'])

    return render_template("homepage.html", days_of_week=days_of_week, breakfast_weekly=breakfast_weekly, lunch_weekly=lunch_weekly, dinner_weekly=dinner_weekly, dessert_weekly=dessert_weekly)

@app.route("/switch", methods=["POST"])
@login_required
def switch():

    user_id = session["user_id"]
    days_of_week = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    row_count = db.execute("SELECT COUNT(*) FROM weekly")[0]['COUNT(*)']

    category = request.form.get("food_category")
    switch_meal = request.form.get("switch_meal")
    new_meal = request.form.get("new_meal")

    # Check for mistakes:

    if category=="Food category":
        flash("You must select a category")
        return redirect("/")
    if not switch_meal:
        flash("You must select a meal to switch")
        return redirect("/")
    if not new_meal:
        flash("You must select a new meal")
        return redirect("/")

    name_exists1 = db.execute("SELECT 1 FROM recipes WHERE name=:name and user_id=:user_id", user_id=user_id, name=switch_meal)
    name_exists2 = db.execute("SELECT 1 FROM recipes WHERE name=:name and user_id=:user_id", user_id=user_id, name=new_meal)

    if not name_exists1:
        flash("The recipe name doesn't exist")
        return redirect("/")
    if not name_exists2:
        flash("The recipe name doesn't exist")
        return redirect("/")

    db.execute("UPDATE weekly SET name=:new_meal WHERE user_id=:user_id AND category=:category AND name=:switch_meal", new_meal=new_meal, user_id=user_id, category=category, switch_meal=switch_meal)

    if row_count > 0:
        breakfast_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Breakfast' AND user_id=:user_id", user_id=user_id)
        lunch_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Lunch' AND user_id=:user_id", user_id=user_id)
        dinner_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Dinner' AND user_id=:user_id", user_id=user_id)
        dessert_weekly = db.execute("SELECT id, name, active_day, category, user_id FROM weekly WHERE category='Dessert' AND user_id=:user_id", user_id=user_id)

        return render_template("homepage.html", days_of_week=days_of_week, breakfast_weekly=breakfast_weekly, lunch_weekly=lunch_weekly, dinner_weekly=dinner_weekly, dessert_weekly=dessert_weekly)
    else:
        flash("You must generate a meal plan first")
        return redirect("/")

@app.route("/shopping",methods=["GET", "POST"])
@login_required
def shopping():
    user_id = session["user_id"]

    if request.method == "POST":
        app.logger.debug('/shopping called, request method %s, user id %d', request.method, user_id)

        row_count = db.execute("SELECT COUNT(*) FROM weekly")[0]['COUNT(*)']

        if row_count == 0:
            flash("You must generate a meal plan first")
            return redirect("/")


        if row_count > 0:

            shopping_list = db.execute("SELECT ingredients.ingredient, sum(ingredients.quantity), ingredients.measurement FROM ingredients JOIN recipes ON ingredients.id_recipe=recipes.id AND ingredients.user_id=recipes.user_id JOIN weekly ON recipes.name=weekly.name AND recipes.user_id=weekly.user_id WHERE recipes.user_id=:user_id GROUP BY ingredients.ingredient, ingredients.measurement", user_id=user_id)
            app.logger.debug('About to redirect from POST')
            return redirect("/shopping")

    else:
        app.logger.debug('/shopping called, request method %s, user id %d', request.method, user_id)
        shopping_list = db.execute("SELECT ingredients.ingredient, sum(ingredients.quantity), ingredients.measurement FROM ingredients JOIN recipes ON ingredients.id_recipe=recipes.id AND ingredients.user_id=recipes.user_id JOIN weekly ON recipes.name=weekly.name AND recipes.user_id=weekly.user_id WHERE recipes.user_id=:user_id GROUP BY ingredients.ingredient, ingredients.measurement", user_id=user_id)
        app.logger.debug('About to redirect from GET')
        return render_template("shopping.html", shopping_list = shopping_list)
















