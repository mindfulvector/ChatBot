import os
import datetime
import json
import pprint
from flask import Flask, request, render_template, redirect, url_for, flash, sessions, session
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from itsdangerous import URLSafeTimedSerializer
import smtplib
from email.mime.text import MIMEText
import openai
import tiktoken
from uuid import uuid4
from markdown import markdown

from models import db, User, ChatSession, Message

pp=pprint.PrettyPrinter()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////mnt/d/Dev/Projects/Python/chat.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY')
app.config['SMTP_HOST'] = os.environ.get('SMTP_HOST')
app.config['SMTP_FROM'] = os.environ.get('SMTP_USERNAME')
app.config['SMTP_USERNAME'] = os.environ.get('SMTP_USERNAME')
app.config['SMTP_PASSWORD'] = os.environ.get('SMTP_PASSWORD')
app.config['SMTP_PORT'] = os.environ.get('SMTP_PORT')

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

openai.api_key = app.config['OPENAI_API_KEY']

def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    num_tokens = len(encoding.encode(string))
    return num_tokens

def num_tokens_from_messages(messages) -> int:
    """Returns the number of tokens for all messages in a list."""
    num_tokens = 0
    for msg in messages:
        num_tokens += num_tokens_from_string(msg['content'])
    return num_tokens

@app.template_filter('markdown')
def markdown_filter(text):
    # Ensure the Markdown is safely converted, escaping any raw HTML
    return markdown(text, extensions=['fenced_code', 'codehilite'])

# Load a user
@login_manager.user_loader
def load_user(user_id):
    return User.query.filter_by(id=int(user_id)).first()

# Main UI
@app.route('/', methods=['GET', 'POST'])
@app.route('/chat/<int:session_id>/', methods=['GET', 'POST'])
@login_required  # Require login for this view
def index(session_id=None):
    sessions = []
    messages = []
    if request.method == 'POST':
        user_message = request.form['user_message']
        new_tokens = num_tokens_from_string(user_message)

        print('find current_session with id='+str(session_id) + ' and user_id='+str(current_user.id))
        current_session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
        print('session.id='+str(current_session.id))

        message = Message(role='user', content=user_message, chat_session_id=current_session.id, user_id=current_user.id)

        print('user:'+json.dumps(message.as_dict()))
        db.session.add(message)
        db.session.commit()

        print('current_session.chat_type: ' + current_session.chat_type)

        # Construct list of messages to send to open API
        # First, system messages from the chat type
        if 'GAME' == current_session.chat_type:
            system_messages = [
                {'role': 'system', 
                    'content': 'You are a text adventure game interpreter. '
                   +'You can understand a limited range of valid commands. '
                   +'The only valid commands: NEW GAME, LOOK [AT] [NOUN], GET [NOUN], DROP [NOUN], INVENTORY, EXAMINE [NOUN]. '
                   +'You respond as a DOS text adventure game written in 1990s would respond. '
                   +'A NOUN is only valid if it appears in the description you provided of the current room or is in the user\'s inventory. '
                   +'You keep track of items the user has (via the GET command) and print a list when they say "INVENTORY". '
                   +'You remove a NOUN from this list when the user says "DROP [NOUN]".'
                   +'Words such as "THE" are optional in commands and you totally ignore as if they were not there.'
                   +'If the user specifies a NOUN you haven\'t mentioned exactly that way you ask them to be more clear.'
                   +'When the user prints NEW GAME, respond with a made up title screen for a text adventure game, then ask the user their name. After they provide their name, provide the first room description of the made up game.'
                }
            ]
        else:
            system_messages = []
        
        system_tokens = num_tokens_from_messages(system_messages)
        
        # Get history messages from this chat        
        messages = Message.query.filter_by(chat_session_id=current_session.id, user_id=current_user.id).all()
        history_messages = [{'role': msg.role, 'content': msg.content} for msg in messages]
        print('context token count with new tokens is '+str(new_tokens + num_tokens_from_messages(history_messages)))
        while new_tokens + system_tokens + num_tokens_from_messages(history_messages) > 3500:
            # Remove a message and re-restimate
            history_messages.pop(0)                  # shift / pop from first
            print('reduce token count to '+str(new_tokens + system_tokens + num_tokens_from_messages(history_messages)))

        print('***** context *****')
        print('first message in list is ' + json.dumps(history_messages[0]))
        print('last message in list is ' + json.dumps(history_messages[len(history_messages)-1]))

        combined_messages = system_messages + history_messages

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=combined_messages
        )
        assistant_message = Message(role='assistant', 
            content=response['choices'][0]['message']['content'],
            chat_session_id=current_session.id,
            user_id=current_user.id)
        print('bot:'+json.dumps(assistant_message.as_dict()))
        db.session.add(assistant_message)
        db.session.commit()
        return redirect(url_for('index', session_id=current_session.id))
    else:
        sessions = ChatSession.query.filter_by(user_id=current_user.id).all()
        if sessions:
            print('sessions: ' + ','.join(map(lambda sess: 'session#'+str(sess.id), sessions)))
        
        print('get session <id='+str(session_id) + ', user_id='+str(current_user.id) + '>')
        
        current_session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
        if current_session:
            print('current_session='+json.dumps(current_session.as_dict()))

            print('fetch messages for session ' + str(session_id) + ' if owned by user ' + str(current_user.id))

            messages = Message.query.filter_by(chat_session_id=current_session.id, user_id=current_user.id).all()
            print('got messages ' + str(len(messages)) + ': ' + ','.join(map(lambda msg: 'msg#'+str(msg.id), messages)))
            
    return render_template('index.html', sessions=sessions, messages=messages, current_session=current_session, current_session_id=session_id)

# Delete a message
@app.route('/delete_msg/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    Message.query.filter_by(user_id=current_user.id, id=message_id).delete()
    db.session.commit()
    return 'OK'

# Delete a chat and all messages
@app.route('/delete_chat/<int:session_id>', methods=['POST'])
@login_required
def delete_chat(session_id):
    ChatSession.query.filter_by(user_id=current_user.id, id=session_id).delete()
    Message.query.filter_by(user_id=current_user.id, chat_session_id=session_id).delete()
    db.session.commit()
    return 'OK'


# Create a new chat session
@app.route('/new_chat/<chat_type>')
@login_required
def new_chat(chat_type='GENERAL'):
    new_session = ChatSession(user_id=current_user.id, chat_type=chat_type)
    db.session.add(new_session)
    db.session.commit()
    return redirect(url_for('index', session_id=new_session.id))

# Used to register and login to accounts
def send_magic_link(email):
    print('send_magic_link on server ' + app.config['SMTP_HOST'] + ':' + str(app.config['SMTP_PORT']) + ' with username ' + app.config['SMTP_USERNAME'] + ' and password len ' + str(len(app.config['SMTP_PASSWORD'])))

    # Gethe user we've requested a link for
    user = User.query.filter_by(email=email).first()

    # Generate a new token and expiration time
    user.magic_token = str(uuid4())+s.dumps(email, salt='email-confirm')
    user.token_expiration = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    db.session.commit()
    
    # Create the magic link with the token
    magic_link = url_for('verify', magic_token=user.magic_token, _external=True)
    
    msg = MIMEText(f'Click the link to log in: {magic_link}')

    msg['Subject'] = 'ChatBot - Magic Login Link'
    msg['From'] = app.config['SMTP_FROM']
    msg['To'] = email
    print('SMTP create')
    server = smtplib.SMTP_SSL(app.config['SMTP_HOST'], app.config['SMTP_PORT'])
    print('SMTP server created')
    server.set_debuglevel(1)
    print('SMTP login')
    server.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
    print('SMTP send_message')
    server.send_message(msg)

# Login or login into an account
@app.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email)
            db.session.add(user)
            db.session.commit()
        send_magic_link(email)
        flash('Magic link sent to your email. Click this link to be logged in.', 'info')
        return redirect(url_for('login'))
    return render_template('login.html')

# Complete login to a user account
@app.route('/verify/<magic_token>/')
def verify(magic_token):
    user = User.query.filter_by(magic_token=magic_token).first()
    if user and user.token_expiration > datetime.datetime.utcnow():
        # Token is valid
        login_user(user)
        user.magic_token = None  # Clear the token
        user.token_expiration = None
        db.session.commit()
        flash('Logged in successfully.', 'success')
        return redirect(url_for('index'))
    else:
        flash('The magic link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))


@app.route('/logout')
def logout():
    # Perform logout logic here, such as clearing session data
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
