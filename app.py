from flask import Flask
import os
from routes import bp as main_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Register blueprint
app.register_blueprint(main_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
