import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import create_engine, desc
from sqlalchemy_utils import database_exists, create_database

app = Flask(__name__)

# Database configuration for Render
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    database_url += "?sslmode=require"
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///garden.db'

# Database optimization settings
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 20,
    'pool_timeout': 30,
    'pool_recycle': 1800,
    'max_overflow': 10
}

db = SQLAlchemy(app)

class SensorReadings(db.Model):
    __tablename__ = 'sensor_readings'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    soil_moisture = db.Column(db.Integer, nullable=False)
    water_flow = db.Column(db.Float, nullable=False)
    valve_state = db.Column(db.Boolean, default=False, nullable=False)

    @staticmethod
    def cleanup_old_readings():
        """Delete readings older than 24 hours"""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        SensorReadings.query.filter(SensorReadings.timestamp < cutoff).delete()
        db.session.commit()

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    moisture_threshold = db.Column(db.Integer, default=500, nullable=False)
    watering_duration = db.Column(db.Integer, default=10, nullable=False)
    timer_enabled = db.Column(db.Boolean, default=False, nullable=False)
    timer_hour = db.Column(db.Integer, default=0, nullable=False)
    timer_minute = db.Column(db.Integer, default=0, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Commands(db.Model):
    __tablename__ = 'commands'
    id = db.Column(db.Integer, primary_key=True)
    valve_state = db.Column(db.Boolean, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    executed = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    command_type = db.Column(db.String(20), default='manual')  # manual, timer, or moisture

def init_database():
    try:
        engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
        if not database_exists(engine.url):
            create_database(engine.url)
        db.create_all()
        
        # Create default settings if not exists
        if not Settings.query.first():
            default_settings = Settings(
                moisture_threshold=500,
                watering_duration=10,
                timer_enabled=False,
                timer_hour=6,
                timer_minute=0
            )
            db.session.add(default_settings)
            db.session.commit()
    except Exception as e:
        print(f"Database initialization error: {e}")

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
            water_flow=data['water_flow'],
            valve_state=data.get('valve_state', False)
        )
        db.session.add(reading)
        db.session.commit()

        # Cleanup old readings periodically
        if reading.id % 100 == 0:  # Every 100 readings
            SensorReadings.cleanup_old_readings()

        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_commands', methods=['GET'])
def get_commands():
    try:
        # Get all unexecuted commands, ordered by timestamp
        commands = Commands.query.filter_by(executed=False).order_by(Commands.timestamp.desc()).all()
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
        
        if commands:
            # Get the most recent command
            latest_command = commands[0]
            for command in commands:
                command.executed = True
            
            db.session.commit()
            
            response_data.update({
                'valve_state': latest_command.valve_state,
                'duration': latest_command.duration,
                'command_type': latest_command.command_type
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
            duration=data.get('duration', 0),
            command_type='manual'
        )
        db.session.add(command)
        db.session.commit()
        return jsonify({'status': 'success', 'command_id': command.id})
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
            'timer_minute': settings.timer_minute,
            'last_updated': settings.last_updated.isoformat()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/readings', methods=['GET'])
def get_readings():
    try:
        # Get the latest reading
        reading = SensorReadings.query.order_by(desc(SensorReadings.timestamp)).first()
        
        if reading:
            return jsonify({
                'temperature': reading.temperature,
                'humidity': reading.humidity,
                'soil_moisture': reading.soil_moisture,
                'water_flow': reading.water_flow,
                'valve_state': reading.valve_state,
                'timestamp': reading.timestamp.isoformat()
            })
        return jsonify({})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/readings/history', methods=['GET'])
def get_readings_history():
    try:
        # Get readings from the last hour
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        readings = SensorReadings.query.filter(
            SensorReadings.timestamp >= hour_ago
        ).order_by(SensorReadings.timestamp.desc()).all()
        
        return jsonify([{
            'temperature': r.temperature,
            'humidity': r.humidity,
            'soil_moisture': r.soil_moisture,
            'water_flow': r.water_flow,
            'valve_state': r.valve_state,
            'timestamp': r.timestamp.isoformat()
        } for r in readings])
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
