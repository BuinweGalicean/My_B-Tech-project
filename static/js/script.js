// Camera handling
let stream = null;
async function waitForVideoReady(video) {
  if (video.readyState >= 2) {
    return;
  }
  return new Promise(resolve => {
    const onReady = () => {
      video.removeEventListener('loadedmetadata', onReady);
      resolve();
    };
    video.addEventListener('loadedmetadata', onReady);
  });
}

function setFaceGuide(message, visible = true) {
  const guide = document.getElementById('faceGuide');
  if (!guide) return;
  guide.textContent = message;
  guide.classList.toggle('hidden', !visible);
}

function setScanStatus(message, status = 'info', visible = true) {
  const statusEl = document.getElementById('scanStatus');
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.className = `scan-status ${status}${visible ? '' : ' hidden'}`;
}

function runScanEffect(active) {
  const preview = document.querySelector('.camera-preview');
  if (!preview) return;
  preview.classList.toggle('scanning', active);
}

async function startCamera() {
  const video = document.getElementById('camera');
  const overlay = document.getElementById('faceOverlay');
  if (stream) {
    video.classList.remove('hidden');
    if (overlay) overlay.classList.remove('hidden');
    setFaceGuide('Move your face inside the circle. Move your head up or down slowly until your face is centered.');
    setScanStatus('Ready to scan', 'info', true);
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = stream;
    video.classList.remove('hidden');
    if (overlay) overlay.classList.remove('hidden');
    setFaceGuide('Move your face inside the circle. Move your head up or down slowly until your face is centered.');
    setScanStatus('Ready to scan', 'info', true);
    await waitForVideoReady(video);
    await video.play();
  } catch (e) {
    alert('Camera access failed: ' + e.message);
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
    stream = null;
  }
  const video = document.getElementById('camera');
  const overlay = document.getElementById('faceOverlay');
  if (video) video.classList.add('hidden');
  if (overlay) overlay.classList.add('hidden');
  runScanEffect(false);
}

async function captureImage() {
  const video = document.getElementById('camera');
  if (!stream) {
    await startCamera();
  }
  await waitForVideoReady(video);
  const canvas = document.getElementById('canvas');
  const width = video.videoWidth || 640;
  const height = video.videoHeight || 480;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, width, height);
  return canvas.toDataURL('image/png');
}

async function sendFace(imageData) {
  const res = await fetch('/capture-face', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_data: imageData }) });
  return res.json();
}

let scanInProgress = false;

async function autoVerifyFace() {
  const faceRecognitionAvailable = document.body.dataset.faceRecognition === 'true';
  const startScanBtn = document.getElementById('startScan');

  if (!faceRecognitionAvailable) {
    setScanStatus('Face recognition is not available on the server.', 'error', true);
    return;
  }

  if (scanInProgress) return;
  scanInProgress = true;
  if (startScanBtn) {
    startScanBtn.disabled = true;
    startScanBtn.textContent = 'Scanning...';
  }

  await startCamera();
  setFaceGuide('Position your face inside the circle. Scanning will begin automatically.');
  setScanStatus('Preparing face scan...', 'info', true);
  runScanEffect(true);
  await new Promise(resolve => setTimeout(resolve, 1200));
  setScanStatus('Scanning your face...', 'active', true);
  await new Promise(resolve => setTimeout(resolve, 900));

  const img = await captureImage();
  const res = await sendFace(img);
  runScanEffect(false);

  if (res.success) {
    if (startScanBtn) {
      startScanBtn.textContent = 'Scan Successful';
    }
    setScanStatus('Face captured successfully. Redirecting...', 'success', true);
    setFaceGuide('Face scan complete. Redirecting you now.');
    await new Promise(resolve => setTimeout(resolve, 800));
    window.location.href = res.redirect || '/vote';
    return;
  }

  if (startScanBtn) {
    startScanBtn.disabled = false;
    startScanBtn.textContent = 'Retry Face Scan';
  }
  setScanStatus('Scan failed. Please try again.', 'error', true);
  setFaceGuide('Face scan failed. Adjust your position and press Retry Face Scan.');
  alert(res.message || 'Face verification failed.');
  scanInProgress = false;
}

async function startFaceScan() {
  const faceRecognitionAvailable = document.body.dataset.faceRecognition === 'true';

  if (!faceRecognitionAvailable) {
    alert('Face recognition support is not available on the server. Please install required dependencies and restart the app.');
    return;
  }

  await autoVerifyFace();
}

document.addEventListener('DOMContentLoaded', async () => {
  const loggedIn = document.body.dataset.loggedIn === 'true';
  const requireLogin = () => {
    if (!loggedIn) {
      alert('Please log in first to capture biometric data or upload your ID card.');
      return false;
    }
    return true;
  };

  const faceRecognitionAvailable = document.body.dataset.faceRecognition === 'true';

  const biometricVerified = document.body.dataset.biometrics === 'true';

  const startScanBtn = document.getElementById('startScan');
  if (startScanBtn) {
    startScanBtn.addEventListener('click', async () => {
      if (!requireLogin()) return;
      if (!faceRecognitionAvailable) {
        alert('Face recognition support is not available on the server. Please install requirements and restart the app.');
        return;
      }
      await autoVerifyFace();
    });
  }

  document.querySelectorAll('.vote-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      if (!requireLogin()) {
        e.preventDefault();
        return;
      }
      if (!biometricVerified) {
        e.preventDefault();
        alert('You must complete face verification before voting.');
        return;
      }
    });
  });



  const currentPage = document.body.dataset.page;
  if (currentPage === 'verify' && faceRecognitionAvailable) {
    await startCamera();
    setFaceGuide('Camera is ready. Press Start Face Scan when you are ready.');
    setScanStatus('Camera opened. Click Start Face Scan to begin.', 'info', true);
  }

  if (currentPage === 'register' && faceRecognitionAvailable) {
    const registerCamera = document.getElementById('registerCamera');
    const registerOverlay = document.getElementById('registerFaceOverlay');
    const registerGuide = document.getElementById('registerFaceGuide');
    const registerStatus = document.getElementById('registerScanStatus');
    const faceImageField = document.getElementById('faceImageData');
    const registerCaptureArea = document.getElementById('registerCaptureArea');
    const startRegisterCapture = document.getElementById('startRegisterCapture');

    const requiredFields = [
      document.querySelector('input[name="first_name"]'),
      document.querySelector('input[name="last_name"]'),
      document.querySelector('input[name="id_number"]'),
      document.querySelector('input[name="phone"]'),
      document.querySelector('input[name="email"]')
    ].filter(Boolean);

    let registerCameraStarted = false;
    let registerScanInProgress = false;

    const setRegisterStatus = (message, status) => {
      if (!registerStatus) return;
      registerStatus.textContent = message;
      registerStatus.className = `scan-status ${status}`;
    };

    const startRegisterCamera = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        registerCamera.srcObject = stream;
        registerCamera.classList.remove('hidden');
        if (registerOverlay) registerOverlay.classList.remove('hidden');
        if (registerGuide) registerGuide.classList.remove('hidden');
        if (registerCaptureArea) registerCaptureArea.classList.remove('hidden');
        if (startRegisterCapture) startRegisterCapture.textContent = 'Capture Face';
        setRegisterStatus('Camera ready. Press Scan Face to capture your face.', 'info');
        await waitForVideoReady(registerCamera);
        await registerCamera.play();
        registerCameraStarted = true;
      } catch (e) {
        alert('Camera access failed: ' + e.message);
      }
    };

    const stopRegisterCamera = () => {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
      }
      if (registerCamera) registerCamera.classList.add('hidden');
      if (registerOverlay) registerOverlay.classList.add('hidden');
      if (registerCaptureArea) registerCaptureArea.classList.add('hidden');
      registerCameraStarted = false;
      registerScanInProgress = false;
    };

    const captureRegisterImage = async () => {
      if (registerScanInProgress) {
        return;
      }

      if (!registerCameraStarted) {
        await startRegisterCamera();
      }

      if (!registerCameraStarted) {
        return;
      }

      registerScanInProgress = true;
      if (startRegisterCapture) {
        startRegisterCapture.disabled = true;
        startRegisterCapture.textContent = 'Scanning...';
      }
      setRegisterStatus('Scanning your face for 5 seconds. Keep your head centered.', 'active');
      if (registerGuide) {
        registerGuide.textContent = 'Keep your head centered, eyes forward, and stay still while scanning.';
      }

      await waitForVideoReady(registerCamera);

      let countdown = 5;
      const countdownInterval = setInterval(() => {
        countdown -= 1;
        if (countdown > 0) {
          setRegisterStatus(`Scanning... ${countdown}s remaining`, 'active');
        }
      }, 1000);

      await new Promise(resolve => setTimeout(resolve, 5000));
      clearInterval(countdownInterval);

      if (!registerCameraStarted) {
        setRegisterStatus('Camera stopped unexpectedly. Please retry scan.', 'error');
        if (startRegisterCapture) {
          startRegisterCapture.disabled = false;
          startRegisterCapture.textContent = 'Retry Scan';
        }
        registerScanInProgress = false;
        return;
      }

      const canvas = document.createElement('canvas');
      canvas.width = registerCamera.videoWidth || 640;
      canvas.height = registerCamera.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(registerCamera, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL('image/png');

      const qualityOk = dataUrl && dataUrl.length > 5000;
      if (!qualityOk) {
        setRegisterStatus('Scan quality was not sufficient. Please try again.', 'error');
        if (startRegisterCapture) {
          startRegisterCapture.disabled = false;
          startRegisterCapture.textContent = 'Retry Scan';
        }
        registerScanInProgress = false;
        return;
      }

      if (faceImageField) faceImageField.value = dataUrl;
      setRegisterStatus('Face captured successfully. Camera closed. Submit the form to complete registration.', 'success');
      if (startRegisterCapture) {
        startRegisterCapture.disabled = false;
        startRegisterCapture.textContent = 'Rescan Face';
      }
      stopRegisterCamera();
    };

    if (startRegisterCapture) {
      startRegisterCapture.addEventListener('click', async () => {
        await captureRegisterImage();
      });
    }
  }

  if (currentPage === 'index' && loggedIn && !biometricVerified) {
    window.location.href = '/verify';
  }

  const siteMenuToggle = document.getElementById('siteMenuToggle');
  const siteMenu = document.getElementById('siteMenu');
  if (siteMenuToggle && siteMenu) {
    siteMenuToggle.addEventListener('click', (event) => {
      event.stopPropagation();
      const isOpen = siteMenu.classList.toggle('open');
      siteMenuToggle.setAttribute('aria-expanded', isOpen);
    });

    document.addEventListener('click', (event) => {
      if (!siteMenu.contains(event.target) && !siteMenuToggle.contains(event.target)) {
        siteMenu.classList.remove('open');
        siteMenuToggle.setAttribute('aria-expanded', 'false');
      }
    });
  }
});