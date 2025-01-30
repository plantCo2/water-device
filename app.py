import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///garden.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
# Database Models
class SensorReadings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    soil_moisture = db.Column(db.Integer)
    water_flow = db.Column(db.Float)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moisture_threshold = db.Column(db.Integer, default=300)
    watering_duration = db.Column(db.Integer, default=30)
    timer_enabled = db.Column(db.Boolean, default=False)
    timer_hour = db.Column(db.Integer, default=0)
    timer_minute = db.Column(db.Integer, default=0)

class Commands(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    valve_state = db.Column(db.Boolean)
    duration = db.Column(db.Integer)
    executed = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/update_readings', methods=['POST'])
def update_readings():
    data = request.get_json()
    reading = SensorReadings(
        temperature=data['temperature'],
        humidity=data['humidity'],
        soil_moisture=data['soil_moisture'],
        water_flow=data['water_flow']
    )
    db.session.add(reading)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/get_commands', methods=['GET'])
def get_commands():
    command = Commands.query.filter_by(executed=False).first()
    settings = Settings.query.first()
    
    if command:
        command.executed = True
        db.session.commit()
        return jsonify({
            'valve_state': command.valve_state,
            'duration': command.duration,
            'timer_enabled': settings.timer_enabled,
            'timer_hour': settings.timer_hour,
            'timer_minute': settings.timer_minute,
            'threshold': settings.moisture_threshold,
            'watering_duration': settings.watering_duration
        })
    return jsonify({
        'timer_enabled': settings.timer_enabled,
        'timer_hour': settings.timer_hour,
        'timer_minute': settings.timer_minute,
        'threshold': settings.moisture_threshold,
        'watering_duration': settings.watering_duration
    })

@app.route('/api/valve/control', methods=['POST'])
def control_valve():
    data = request.get_json()
    command = Commands(
        valve_state=data['state'],
        duration=data.get('duration', 0)
    )
    db.session.add(command)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        data = request.get_json()
        settings = Settings.query.first()
        if not settings:
            settings = Settings()
            db.session.add(settings)
        settings.moisture_threshold = data['threshold']
        settings.watering_duration = data['watering_duration']
        settings.timer_enabled = data['timer_enabled']
        settings.timer_hour = data['timer_hour']
        settings.timer_minute = data['timer_minute']
        db.session.commit()
        return jsonify({'status': 'success'})
    
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)
        db.session.commit()
    return jsonify({
        'threshold': settings.moisture_threshold,
        'watering_duration': settings.watering_duration,
        'timer_enabled': settings.timer_enabled,
        'timer_hour': settings.timer_hour,
        'timer_minute': settings.timer_minute
    })

@app.route('/api/readings', methods=['GET'])
def get_readings():
    reading = SensorReadings.query.order_by(SensorReadings.timestamp.desc()).first()
    if reading:
        return jsonify({
            'temperature': reading.temperature,
            'humidity': reading.humidity,
            'soil_moisture': reading.soil_moisture,
            'water_flow': reading.water_flow,
            'timestamp': reading.timestamp.isoformat()
        })
    return jsonify({})

if __name__ == '__main__':
    app.run(debug=True)
