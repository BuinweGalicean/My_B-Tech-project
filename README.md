# Secure Voting System

Quick setup:

1. Use Python 3.10 or 3.11 in a virtual environment, then install dependencies:

```bash
python -m pip install -r requirement.txt
```

> On Windows, `face-recognition` requires `dlib`, which may need Visual Studio C++ Build Tools and CMake. If those are not installed, use Python 3.10 for the best compatibility.

2. Start MySQL (XAMPP) and import `db_init.sql` or let the app create tables automatically.

3. Run the app:

```bash
python app.py
```

4. Open http://localhost:5000 in your browser.

Notes:
- The app stores uploaded images and biometrics in the database as blobs.
- Biometric capture uses the browser camera to capture images and posts base64 to the server.
- For production you must enable HTTPS, secure sessions, and hardened biometric verification.
