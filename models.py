from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import datetime
from uuid import uuid4

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    magic_token = db.Column(db.String(100), unique=True, nullable=True)
    token_expiration = db.Column(db.DateTime, nullable=True)
    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='chat_owner')
    messages = db.relationship('Message', backref='chat_session', lazy=True)
    chat_type = db.Column(db.String(10), nullable=False, default='GENERAL')
    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    chat_session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='user_owner')
    role = db.Column(db.String(10), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    
    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
