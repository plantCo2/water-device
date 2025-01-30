import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database

app = Flask(__name__)

# Database configuration for Render
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Convert postgres:// to postgresql:// for Render
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    database_url += "?sslmode=require"  # Add SSL mode for Render
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///garden.db'

# Database optimization settings
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_timeout': 30,
    'pool_recycle': 1800,
}

db = SQLAlchemy(app)

# Database Models
class SensorReadings(db.Model):
    __tablename__ = 'sensor_readings'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    soil_moisture = db.Column(db.Integer, nullable=False)
    water_flow = db.Column(db.Float, nullable=False)

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    moisture_threshold = db.Column(db.Integer, default=300, nullable=False)
    watering_duration = db.Column(db.Integer, default=30, nullable=False)
    timer_enabled = db.Column(db.Boolean, default=False, nullable=False)
    timer_hour = db.Column(db.Integer, default=0, nullable=False)
    timer_minute = db.Column(db.Integer, default=0, nullable=False)

class Commands(db.Model):
    __tablename__ = 'commands'
    id = db.Column(db.Integer, primary_key=True)
    valve_state = db.Column(db.Boolean, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    executed = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

def init_database():
    """Initialize database and tables"""
    try:
        engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
        if not database_exists(engine.url):
            create_database(engine.url)
        db.create_all()
        
        # Create default settings if not exists
        if not Settings.query.first():
            default_settings = Settings()
            db.session.add(default_settings)
            db.session.commit()
    except Exception as e:
        print(f"Database initialization error: {e}")

# Initialize database within application context
with app.app_context():
    init_database()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/update_readings', methods=['POST'])
def update_readings():
    try:
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
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_commands', methods=['GET'])
def get_commands():
    try:
        command = Commands.query.filter_by(executed=False).first()
        settings = Settings.query.first()
        
        if not settings:
            settings = Settings()
            db.session.add(settings)
            db.session.commit()
        
        response_data = {
            'timer_enabled': settings.timer_enabled,
            'timer_hour': settings.timer_hour,
            'timer_minute': settings.timer_minute,
            'threshold': settings.moisture_threshold,
            'watering_duration': settings.watering_duration
        }
        
        if command:
            command.executed = True
            db.session.commit()
            response_data.update({
                'valve_state': command.valve_state,
                'duration': command.duration
            })
            
        return jsonify(response_data)
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/valve/control', methods=['POST'])
def control_valve():
    try:
        data = request.get_json()
        command = Commands(
            valve_state=data['state'],
            duration=data.get('duration', 0)
        )
        db.session.add(command)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    try:
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
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/readings', methods=['GET'])
def get_readings():
    try:
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
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Health check endpoint for Render
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
