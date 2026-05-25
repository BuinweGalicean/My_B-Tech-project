let voteChart = null;

async function loadChart() {
  const resp = await fetch('/api/results');
  const data = await resp.json();

  const labels = data.map(d => d.name);
  const votes = data.map(d => d.votes);
  const colors = data.map(d => d.party_color || '#888');

  const ctx = document.getElementById('voteChart').getContext('2d');
  if (voteChart) voteChart.destroy();
  voteChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Votes', data: votes, backgroundColor: colors }]
    },
    options: { responsive: true, scales: { y: { beginAtZero: true } } }
  });
}

// File previews for ID card uploads
function previewFile(inputEl, imgElId) {
  const file = inputEl.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => document.getElementById(imgElId).src = e.target.result;
  reader.readAsDataURL(file);
}

// Upload file to server (voter must be logged-in session-wise)
async function uploadCard(side, file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  fd.append('side', side);
  const res = await fetch('/upload-voting-card', { method: 'POST', body: fd });
  return res.json();
}

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

document.addEventListener('DOMContentLoaded', () => {
  const loggedIn = document.body.dataset.loggedIn === 'true';
  const requireLogin = () => {
    if (!loggedIn) {
      alert('Please log in first to capture biometric data or upload your ID card.');
      return false;
    }
    return true;
  };

  const cardFrontInput = document.getElementById('cardFront');
  const cardBackInput = document.getElementById('cardBack');
  const btnUploadFront = document.getElementById('btnUploadFront');
  const btnUploadBack = document.getElementById('btnUploadBack');
  const startCameraBtn = document.getElementById('startCamera');
  const captureFaceBtn = document.getElementById('captureFace');
  const faceRecognitionAvailable = document.body.dataset.faceRecognition === 'true';

  if (cardFrontInput) {
    cardFrontInput.addEventListener('change', e => {
      previewFile(e.target, 'previewFront');
      if (loggedIn) uploadCard('front', e.target.files[0]);
    });
  }
  if (cardBackInput) {
    cardBackInput.addEventListener('change', e => {
      previewFile(e.target, 'previewBack');
      if (loggedIn) uploadCard('back', e.target.files[0]);
    });
  }

  const biometricVerified = document.body.dataset.biometrics === 'true';

  if (btnUploadFront) {
    btnUploadFront.addEventListener('click', () => {
      if (cardFrontInput) cardFrontInput.click();
    });
  }
  if (btnUploadBack) {
    btnUploadBack.addEventListener('click', () => {
      if (cardBackInput) cardBackInput.click();
    });
  }
  if (startCameraBtn) {
    startCameraBtn.addEventListener('click', startCamera);
  }
  if (captureFaceBtn) {
    if (!faceRecognitionAvailable) {
      captureFaceBtn.disabled = true;
      captureFaceBtn.title = 'Face recognition module is not installed on the server';
    }
    captureFaceBtn.addEventListener('click', async () => {
      if (!requireLogin() || !faceRecognitionAvailable) {
        if (!faceRecognitionAvailable) {
          alert('Face recognition module is not installed on the server. Please install it and restart the app.');
        }
        return;
      }
      await startCamera();
      setFaceGuide('Keep your face inside the circle and move slowly up or down until it fits well.');
      setScanStatus('Preparing scan... Hold still.', 'info', true);
      runScanEffect(true);
      await new Promise(resolve => setTimeout(resolve, 900));
      setScanStatus('Scanning your face...', 'active', true);
      await new Promise(resolve => setTimeout(resolve, 800));
      const img = await captureImage();
      const previewFront = document.getElementById('previewFront');
      if (previewFront) previewFront.src = img; // quick preview
      const res = await sendFace(img);
      runScanEffect(false);
      stopCamera();
      if (res.success) {
        setScanStatus('Face verified successfully. Redirecting to vote page...', 'success', true);
        setFaceGuide('Face scan complete. You are being redirected to the voting page.');
        await new Promise(resolve => setTimeout(resolve, 800));
        window.location.href = '/vote';
        return;
      }
      setScanStatus('Scan failed. Please try again.', 'error', true);
      setFaceGuide('Face scan failed. Try again and keep your face centered.');
      alert(res.message || JSON.stringify(res));
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
        alert('You must complete biometric verification to confirm your identity with your ID before voting.');
      }
    });
  });

  const refreshChartButton = document.getElementById('refreshChart');
  if (refreshChartButton) {
    refreshChartButton.addEventListener('click', loadChart);
  }

  // Auto load chart on page
  loadChart();
});