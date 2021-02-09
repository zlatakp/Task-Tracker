import os
import smtplib
from email.message import EmailMessage
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, json
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from helpers import login_required

#please provide gmail login credentials to use for sending information to the user, i.e. in case of password reset
login_email=""
login_password =""


app= Flask(__name__)

db = SQL("sqlite:///employees.db")

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

#Homepage
@app.route("/", methods = ["GET", "POST"])
@login_required
def homepage():
    #User ID of the person currently login
    user_id = session['user_id']


    #When submission is made to the homepage (by staff), progress values on each task are extracted
    if request.method == "POST":
        task_number = int(db.execute("SELECT total_tasks FROM progress WHERE id = :user_id", user_id = user_id)[0]['total_tasks'])
        #variables for tracking overall progress and number of tasks complete/incomplete
        overall_progress = 0
        tasks_completed = 0
        tasks_incomplete = 0
        for i in range (1, task_number + 1):
            progress = int(request.form.get("task_"+str(i)))
            overall_progress = overall_progress + progress
            taskprogress_index = "task_" + str(i) + "_status"
            db.execute("UPDATE tasks SET :taskprogress_index = :progress WHERE id = :user_id", taskprogress_index = taskprogress_index, progress = str(progress) + "%", user_id = user_id)
            if progress == 100:
                #if a task was completed, update the number of tasks completed column of the progress table
                tasks_completed += 1
                db.execute("UPDATE progress SET tasks_completed = :tasks_completed WHERE id = :user_id", tasks_completed = tasks_completed, user_id = user_id)
            elif progress < 100:
                #if a task is incomplete, update the number of tasks incomplete column of the progress table
                tasks_incomplete += 1
                db.execute("UPDATE progress SET tasks_incomplete = :tasks_incomplete WHERE id = :user_id", tasks_incomplete = tasks_incomplete, user_id = user_id)

        #update of the overall progress of the employee across all tasks
        try:
            progress_update = overall_progress/task_number
        except ZeroDivisionError:
            progress_update = 0
        db.execute("UPDATE progress SET progress = :progress WHERE id = :user_id", progress = progress_update, user_id = user_id)
        return redirect("/")

    #if request is "GET"
    else:
        rows_info=db.execute("SELECT * FROM employee_info WHERE id = :user_id", user_id = user_id)
        #identify whether a supervisor or staff is currently in session
        access = rows_info[0]['access']
        rows_progress=db.execute("SELECT * FROM progress WHERE id =:user_id", user_id = user_id)
        #create arrays that will hold assigned tasks and progress on each task
        tasks = []
        tasks_progress = []
        # for staff users, extract all tasks and progress for future display on the html page
        if access == "staff":
            task_number = int(db.execute("SELECT total_tasks FROM progress WHERE id = :user_id", user_id = user_id)[0]['total_tasks'])
            rows_tasks = db.execute("SELECT * FROM tasks WHERE id = :user_id", user_id = user_id)
            for i in range(1, task_number + 1):
                task_index = "task_"+ str(i)
                taskprogress_index = '_'.join(['task', str(i), 'status'])
                #append each task to tasks array and respective progress to tasks_progress array
                task = rows_tasks[0][task_index]
                if task != "":
                    tasks.append(task)
                    tasks_progress.append(int((rows_tasks[0][taskprogress_index]).replace("%", "")))
            progress_bar = rows_progress[0]['progress']
            info = ""
        #if access is 'supervisor'
        else:
            #extract staff's tasks, first names, last names and progress so the progress summary of all employees can be displayed in supervisor's homepage
            info = db.execute("SELECT tasks.*, employee_info.first_name, employee_info.last_name, progress.progress FROM tasks LEFT JOIN employee_info ON employee_info.id = tasks.id LEFT JOIN progress ON progress.id = employee_info.id")
            # since supervisors do not get tasks assigned, there is no value for the progress bar
            progress_bar = None
        #return homepage and parse all necessary variables
        return render_template("homepage.html", access=access, tasks = tasks, tasks_progress = tasks_progress, progress = progress_bar, info = info)


#User registration
@app.route("/register", methods=["GET", "POST"])
def register():

    #if the user is attempting to submit a registration form to create a new account
    if request.method == "POST":
        #extract values of all fields
        username = request.form.get("username")
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        password = request.form.get("password")
        access = request.form.get("access")
        rows_username = db.execute("SELECT * FROM employee_info WHERE username = :username", username=username)
        rows_email = db.execute("SELECT * FROM employee_info WHERE email = :email", email=email)

        #check if the username or email already exists in the system, return an error message if either is true
        if len(rows_username) > 0 or len(rows_email) > 0:
            return render_template("error.html", error_message = "Username and/or email already exist")

        #if the username and email do not already exist in the system, proceed with user registration
        else:
            #update 'employee_info' table submitted information from the registration form
            db.execute("INSERT INTO employee_info(username, first_name, last_name, email, password, access) VALUES (:username, :first_name, :last_name, :email, :password, :access)",
            username=username, first_name=first_name, last_name=last_name, email=email, password=password, access=access)

            #if the user is registring for a staff account, also create rows in 'progress' and 'tasks' tables for future tracking
            if access == 'staff':
                user_id = db.execute("SELECT * FROM employee_info WHERE username = :username", username=request.form.get("username"))[0]['id']

                #initialize progress and task status to 0 and name of tasks to an empty string
                db.execute("INSERT INTO progress(id, total_tasks, tasks_completed, tasks_incomplete, progress) VALUES (:user_id, :initial, :initial, :initial, :initial)", user_id = user_id, initial = 0)
                db.execute("INSERT INTO tasks(id, task_1, task_1_status, task_2, task_2_status, task_2, task_2_status,task_3, task_3_status, task_4, task_4_status, task_5, task_5_status) VALUES (:user_id, :notask, :initial, :notask, :initial, :notask, :initial, :notask, :initial, :notask, :initial, :notask, :initial)",
                            user_id = user_id, notask = "", initial = 0)

            #after updating the database, return to the login page
            return render_template("login.html")

    #if the reques is 'GET' render the registration page
    else:
        return render_template("register.html")


#User login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        rows_info=db.execute("SELECT * FROM employee_info WHERE username = :username",
        username = request.form.get("username"))
        password=request.form.get("password")

        #check if the username exists in the system and if the password matches the entered password by the user, if not return error page
        if len(rows_info) != 1 or password != rows_info[0]['password']:
            return render_template("error.html", error_message = "Invalid Username and/or Password")

        #if the username exists and the password matches, update session's user_id to equal to the user's and redirect to the homepage
        else:
            session["user_id"] = rows_info[0]["id"]
            return redirect("/")

    #for a 'GET' request, return the login page
    else:
        return render_template("login.html")

#Reset password
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    #if the user is attempting to submit a reset password request, obtain their email
    if request.method == "POST":
        email=request.form.get('email')
        rows_info = db.execute("SELECT * FROM employee_info WHERE email = :email", email = email)
        #check if the email exists in the database
        if len(rows_info) < 1:
            return render_template("error.html", error_message = 'No account associated with this email address')

        #if the entered email is associated with a user, send the password via Gmail server to the user
        else:
            password = rows_info[0]['password']
            message = EmailMessage()
            message['from'] = login_email
            message['to'] = email
            message['subject'] = 'Password Reset'
            message.set_content("Your password is: "+password)
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(login_email, login_password)
            server.send_message(message)
            #log out and display confirmation of the email containing password sent to the provided email address
            session.clear()
            return render_template("reset.html", email=email)
    else:
        #extract login status information which will be used to determine to content of the navigation bar on the forgot.html page
        login_status = 'in'
        if str(session) == '<FileSystemSession {}>':
            login_status = 'out'
        return render_template("forgot.html", login_status = login_status)

#User log out
@app.route("/logout")
def logout():
    #clear session information and redirect to homepage
    session.clear()
    return redirect("/")

#Assign tasks to employees
@app.route("/assign", methods=["GET", "POST"])
def assign():
    #Post request assigns tasks
    if request.method == "POST":
        #extract first and last name of the employee
        first_name=request.form.get('employee').split()[0]
        last_name=request.form.get('employee').split()[1]

        #extract employee's id
        idval = db.execute("SELECT * FROM employee_info WHERE first_name=:first_name AND last_name = :last_name AND NOT access = 'supervisor'", first_name = first_name, last_name = last_name)[0]['id']

        #extract task list from 'tasks' table for the employee
        taskList = db.execute("SELECT * FROM tasks WHERE id = :idval", idval = idval)[0]


        #iterate through the task list to find empty slots
        #y keeps track of tasks from 'tasks' table
        y = 1
        for key in taskList:
            #creates index for 'tasks' table
            keyName = '_'.join(['task', str(y)])

            if key == keyName:
                #move to the next slot if the current one is not empty
                if taskList[keyName] != "":
                    y = y + 1
        #the number of assigned tasks to the employee, upon completion of the loop equals y - 1

        #using the previously determined empty slot, create indices to be used for SQL queries to insert any assigned tasks
        task_index = '_'.join(['task', str(y)])
        taskprogress_index = '_'.join(['task', str(y), 'status'])
        #initialize progress on a newly assign task to 0
        progress = 0

        #x keeps track of task number from the form
        x = 1
        taskform_index = '_'.join(['task', str(x)])
        task_name = request.form.get(taskform_index)

        #create arrays to keep track of assigned and unassigned tasks in case a supervisor attempts to assign > 5 tasks to an employee
        unassigned = []
        assigned = []

        text_assigned = ""
        #while loop iterates through tasks in the submitted form and extracts those from existing text fields that were not left blank
        while task_name != None and task_name != "":
                #if task slots for an employee have been filled (5 tasks total), keep track of the task in the unassigned array
                if y > 5:
                    unassigned.append(task_name)
                #as long as an employee has empty slots (max of 5), the supervisor may continue assign tasks
                if y < 6:
                    db.execute("UPDATE tasks SET :task_index = :task_name, :taskprogress_index = :progress WHERE id = :idval",
                    task_index = task_index, task_name = task_name, taskprogress_index = taskprogress_index, progress = progress, idval = idval)
                    #update the total number of tasks assigned to a person
                    db.execute("UPDATE progress SET total_tasks = total_tasks + 1 WHERE id = :idval", idval = idval)
                    db.execute("UPDATE progress SET tasks_incomplete = tasks_incomplete + 1 WHERE id = :idval", idval = idval)
                    assigned.append(task_name)

                    #move to the next available spot in the task table to input the task
                    y = y + 1
                    task_index = '_'.join(['task', str(y)])
                    taskprogress_index = '_'.join(['task', str(y), 'status'])

                #move to the next task to be assigned from the form
                x = x + 1
                task = '_'.join(['task', str(x)])
                taskform_index = '_'.join(['task', str(x)])
                task_name = request.form.get(taskform_index)
        #if all tasks were assigned
        if len(unassigned) == 0:
            status = "success"
            text = "All tasks were assigned"
        #if not all tasks were assigned
        else:
            status = "fail"
            text = "The following tasks were not assigned"
            #if some tasks were assigned and some were not
            if len(assigned) != 0:
                text_assigned = "The following tasks were assigned"
        return render_template("assign_result.html", status = status, text = text, text_assigned = text_assigned, unassigned = unassigned, assigned = assigned)

    #If it is a GET request, the page to assign tasks is rendered
    else:
        employees=[]
        #temporary array
        employees_info=db.execute("SELECT id, first_name, last_name FROM employee_info WHERE access = :access", access = "staff")
        #makes a list of employees by first and last name and include number of tasks they currently have assigned
        for employee in employees_info:
            progress = db.execute("SELECT id, total_tasks FROM progress WHERE id = :user_id", user_id = employee['id'])[0]['total_tasks']
            employees.append({'name': ' '.join((employee['first_name'], employee['last_name'])), 'id': employee['id'], 'total_tasks': progress})
        return render_template("assign.html", employees=employees)

#Result of an assigning attempt
@app.route("/assign_result")
def assign_result():
    if request.method == "GET":
        render_template("assign_result.html")

#Employees progress for each task
@app.route("/progress", methods = ["GET", "POST"])
def progress():
    #'POST' method for a supervisor to be directed to employee's detailed progress
    if request.method == "POST":
        user_id = request.form.get("user_id")
        rows_info=db.execute("SELECT * FROM employee_info WHERE id = :user_id", user_id = user_id)
        first_name = rows_info[0]['first_name']
        rows_progress=db.execute("SELECT * FROM progress WHERE id =:user_id", user_id = user_id)

        #arrays will store task name and respective progress submitted by the employee
        tasks = []
        tasks_progress = []
        # for staff users, extract all tasks and progress for future display on the html page
        rows_tasks = db.execute("SELECT * FROM tasks WHERE id = :user_id", user_id = user_id)
        for i in range(1, 6):
            task_index = "task_"+ str(i)
            taskprogress_index  = '_'.join(['task', str(i), 'status'])
            tasks.append(rows_tasks[0][task_index])
            if rows_tasks[0][taskprogress_index] == "assigned":
                tasks_progress.append(0)
            else:
                tasks_progress.append(int((rows_tasks[0][taskprogress_index]).replace("%", "")))
            progress_bar = rows_progress[0]['progress']

        return render_template("progress.html", progress = progress_bar, tasks = tasks, tasks_progress = tasks_progress, first_name = first_name)
    else:
    #Render the page for the 'GET' request
        return render_template("progress.html")
