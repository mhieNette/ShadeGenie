# ShadeGenie Web App

ShadeGenie helps users find the best matching foundation shade by uploading their photo. Users can sign up, log in, and receive shade suggestions based on their uploaded image.

## Features
- User authentication (sign up, log in, log out)
- Upload a photo for shade suggestion
- Simple, modern UI

## How to Run
1. Make sure you have Python 3.7+
2. Install dependencies (already handled if using the provided environment):
   ```
   pip install flask werkzeug
   ```
3. Start the app:
   ```
   python app.py
   ```
4. Open your browser and go to http://127.0.0.1:5000/

## Notes
- The shade suggestion is a placeholder. Replace the logic in `suggest_shade()` in app.py with your ML model or algorithm.
- Uploaded images are stored in `static/uploads/`.

## Security
- This demo uses in-memory user storage. For production, use a database and secure password hashing.
