# Secure Voting System

Quick setup:

1. Use Python 3.10 in a virtual environment, then install dependencies:

```bash
python -m pip install -r requirement.txt
```

> Windows note: This app uses OpenCV for face verification, so you do not need `dlib` or heavy build tools.

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

Windows prerequisites:
- Install Python 3.10 and create a fresh virtual environment.
- If using `face-recognition`, install Visual Studio C++ Build Tools and CMake first.
- Example Windows prereqs:
  1. Install CMake: https://cmake.org/download/
  2. Install Visual Studio Build Tools: https://visualstudio.microsoft.com/downloads/
  3. Then run:

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirement.txt
```
