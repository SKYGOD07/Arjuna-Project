 // Configuration
        const API_URL = 'http://localhost:5000/api';
        
        // Global variables
        let currentLevel = '';
        let trackingMode = '';
        let stream = null;
        let userData = {};
        let currentSessionId = null;
        let isAuthenticated = false;

        // Loading Screen
        window.addEventListener('load', () => {
            setTimeout(() => {
                document.getElementById('loader').classList.add('hidden');
                document.getElementById('mainContent').classList.add('visible');
                checkAuthentication();
            }, 2000);
        });

        // Check authentication status
        async function checkAuthentication() {
            try {
                const response = await fetch(`${API_URL}/auth/check`, {
                    credentials: 'include'
                });
                const data = await response.json();
                
                if (data.authenticated) {
                    isAuthenticated = true;
                    updateUIForAuthentication(data.name);
                }
            } catch (error) {
                console.error('Auth check error:', error);
            }
        }

        function updateUIForAuthentication(name) {
            document.getElementById('authButtons').style.display = 'none';
            document.getElementById('userMenu').classList.add('active');
            document.getElementById('userName').textContent = `Hello, ${name}!`;
        }

        // Navigation
        function goToHome() {
            document.getElementById('homePage').classList.add('active');
            document.getElementById('dashboardPage').classList.remove('active');
        }

        function goToDashboard() {
            if (!isAuthenticated) {
                alert('Please log in to view your dashboard');
                openAuthModal('login');
                return;
            }
            document.getElementById('homePage').classList.remove('active');
            document.getElementById('dashboardPage').classList.add('active');
            loadDashboardData();
        }

        // Auth Modal Functions
        let currentAuthMode = 'signin';

        function openAuthModal(type) {
            currentAuthMode = type;
            const modal = document.getElementById('authModal');
            const title = document.getElementById('authTitle');
            const nameGroup = document.getElementById('nameGroup');
            
            title.textContent = type === 'signin' ? 'Sign Up' : 'Log In';
            nameGroup.style.display = type === 'signin' ? 'block' : 'none';
            
            if (type === 'login') {
                document.getElementById('name').removeAttribute('required');
            } else {
                document.getElementById('name').setAttribute('required', 'required');
            }
            
            modal.classList.add('active');
            document.getElementById('authError').textContent = '';
        }

        function closeAuthModal() {
            document.getElementById('authModal').classList.remove('active');
            document.getElementById('authForm').reset();
        }

        document.getElementById('authForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const name = document.getElementById('name').value;
            
            const endpoint = currentAuthMode === 'signin' ? 'signup' : 'login';
            const payload = currentAuthMode === 'signin' 
                ? { name, email, password }
                : { email, password };
            
            try {
                const response = await fetch(`${API_URL}/auth/${endpoint}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    isAuthenticated = true;
                    updateUIForAuthentication(data.name);
                    closeAuthModal();
                    alert('Authentication successful!');
                } else {
                    document.getElementById('authError').textContent = data.error || 'Authentication failed';
                }
            } catch (error) {
                console.error('Auth error:', error);
                document.getElementById('authError').textContent = 'Network error. Please try again.';
            }
        });

        async function logout() {
            try {
                await fetch(`${API_URL}/auth/logout`, {
                    method: 'POST',
                    credentials: 'include'
                });
                
                isAuthenticated = false;
                document.getElementById('authButtons').style.display = 'flex';
                document.getElementById('userMenu').classList.remove('active');
                goToHome();
                alert('Logged out successfully');
            } catch (error) {
                console.error('Logout error:', error);
            }
        }

        // Level Selection
        function selectLevel(level) {
            if (!isAuthenticated) {
                alert('Please log in or sign up to start tracking');
                openAuthModal('login');
                return;
            }
            
            if (level === 'individual') {
                currentLevel = level;
                document.getElementById('trackingModal').classList.add('active');
            } else {
                alert('This level is coming soon! Currently only Individual tracking is available.');
            }
        }

        function closeTrackingModal() {
            document.getElementById('trackingModal').classList.remove('active');
            document.getElementById('trackingOptions').classList.remove('active');
        }

        // User Data Form
        document.getElementById('userDataForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            userData = {
                age: document.getElementById('age').value,
                weight: document.getElementById('weight').value,
                height: document.getElementById('height').value,
                dietary: document.getElementById('dietary').value,
                goals: document.getElementById('goals').value
            };

            try {
                const response = await fetch(`${API_URL}/profile/save`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify(userData)
                });
                
                if (response.ok) {
                    document.getElementById('trackingOptions').classList.add('active');
                } else {
                    alert('Failed to save profile');
                }
            } catch (error) {
                console.error('Profile save error:', error);
            }
        });

        // Start Tracking
        async function startTracking(mode) {
            trackingMode = mode;
            
            try {
                // Start tracking session in backend
                const response = await fetch(`${API_URL}/tracking/start`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({ mode })
                });
                
                const data = await response.json();
                currentSessionId = data.session_id;
                
                closeTrackingModal();
                
                // Request camera access
                stream = await navigator.mediaDevices.getUserMedia({ 
                    video: { 
                        width: { ideal: 1280 },
                        height: { ideal: 720 }
                    } 
                });
                
                const videoElement = document.getElementById('videoElement');
                videoElement.srcObject = stream;
                
                document.getElementById('cameraContainer').classList.add('active');
                updateStatus(mode);
                document.getElementById('detectionsPanel').style.display = 'block';
                
            } catch (error) {
                console.error('Tracking start error:', error);
                alert('Unable to start tracking. Please ensure camera permissions are granted.');
            }
        }

        function updateStatus(mode) {
            const statusElement = document.getElementById('statusMessage');
            const messages = {
                'cooking': '🍳 Cooking Mode Active: AI is ready to track your cooking process...',
                'eating': '🍽️ Eating Mode Active: AI is monitoring your consumption...',
                'summary': '📊 Analysis Mode Active: AI is analyzing your food data...'
            };
            statusElement.textContent = messages[mode] || 'Camera active...';
        }

        async function captureFrame() {
            const video = document.getElementById('videoElement');
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            
            const imageData = canvas.toDataURL('image/jpeg');
            
            try {
                const response = await fetch(`${API_URL}/tracking/process-frame`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({ image: imageData })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    displayDetections(data.detections);
                    displaySuggestions(data.suggestions);
                    document.getElementById('statusMessage').textContent = '✓ Frame analyzed successfully!';
                    
                    setTimeout(() => updateStatus(trackingMode), 3000);
                }
            } catch (error) {
                console.error('Frame processing error:', error);
                document.getElementById('statusMessage').textContent = '⚠ Analysis failed. Please try again.';
            }
        }

        function displayDetections(detections) {
            const detectionsList = document.getElementById('detectionsList');
            detectionsList.innerHTML = '';
            
            if (detections.length === 0) {
                detectionsList.innerHTML = '<p style="color: #b0b0b0;">No items detected yet</p>';
                return;
            }
            
            detections.forEach(det => {
                const item = document.createElement('div');
                item.className = 'detection-item';
                item.innerHTML = `
                    <strong style="color: #00ff88;">${det.item}</strong>
                    <span style="color: #b0b0b0; float: right;">${(det.confidence * 100).toFixed(1)}%</span>
                `;
                detectionsList.appendChild(item);
            });
        }

        function displaySuggestions(suggestions) {
            if (suggestions && suggestions.length > 0) {
                const statusMsg = document.getElementById('statusMessage');
                statusMsg.textContent += ` | ${suggestions.length} new suggestion(s) available`;
            }
        }

        async function stopTracking() {
            try {
                await fetch(`${API_URL}/tracking/stop`, {
                    method: 'POST',
                    credentials: 'include'
                });
                
                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                }
                
                document.getElementById('cameraContainer').classList.remove('active');
                document.getElementById('detectionsPanel').style.display = 'none';
                
                alert('Tracking stopped! View your analysis in the dashboard.');
                goToDashboard();
                
            } catch (error) {
                console.error('Stop tracking error:', error);
            }
        }

        // Dashboard Functions
        async function loadDashboardData() {
            try {
                const response = await fetch(`${API_URL}/dashboard/stats`, {
                    credentials: 'include'
                });
                const data = await response.json();
                
                updateDashboardStats(data.statistics);
                updateWasteChart(data.waste_data);
                updateDetectionsChart(data.recent_detections);
                updateSuggestionsList(data.suggestions);
                
            } catch (error) {
                console.error('Dashboard load error:', error);
            }
        }

        function updateDashboardStats(stats) {
            document.getElementById('totalSessions').textContent = stats.total_sessions || 0;
            document.getElementById('totalWaste').textContent = (stats.total_waste_kg || 0).toFixed(2);
            document.getElementById('totalConsumed').textContent = (stats.total_food_consumed_kg || 0).toFixed(2);
            document.getElementById('wastePercentage').textContent = (stats.avg_waste_percentage || 0).toFixed(1);
        }

        let wasteChart = null;
        function updateWasteChart(wasteData) {
            const ctx = document.getElementById('wasteChart').getContext('2d');
            
            if (wasteChart) {
                wasteChart.destroy();
            }
            
            wasteChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: wasteData.map(d => d.waste_type),
                    datasets: [{
                        data: wasteData.map(d => d.total_quantity),
                        backgroundColor: [
                            '#00ff88',
                            '#00ccff',
                            '#ff6b6b',
                            '#ffd93d',
                            '#a8dadc'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            labels: {
                                color: '#e0e0e0'
                            }
                        }
                    }
                }
            });
        }

        let detectionsChart = null;
        function updateDetectionsChart(detections) {
            const ctx = document.getElementById('detectionsChart').getContext('2d');
            
            if (detectionsChart) {
                detectionsChart.destroy();
            }
            
            const itemCounts = {};
            detections.forEach(d => {
                itemCounts[d.item_name] = (itemCounts[d.item_name] || 0) + 1;
            });
            
            detectionsChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: Object.keys(itemCounts),
                    datasets: [{
                        label: 'Detection Count',
                        data: Object.values(itemCounts),
                        backgroundColor: '#00ff88'
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            ticks: {
                                color: '#e0e0e0'
                            },
                            grid: {
                                color: '#2a2a3e'
                            }
                        },
                        x: {
                            ticks: {
                                color: '#e0e0e0'
                            },
                            grid: {
                                color: '#2a2a3e'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: '#e0e0e0'
                            }
                        }
                    }
                }
            });
        }

        function updateSuggestionsList(suggestions) {
            const list = document.getElementById('suggestionsList');
            list.innerHTML = '';
            
            if (!suggestions || suggestions.length === 0) {
                list.innerHTML = '<p style="color: #b0b0b0;">No suggestions yet. Start tracking to get personalized AI recommendations!</p>';
                return;
            }
            
            suggestions.forEach(sug => {
                const item = document.createElement('div');
                item.className = 'suggestion-item';
                item.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <p style="color: #e0e0e0;">${sug.suggestion_text}</p>
                        <span class="badge" style="margin-left: 1rem;">${sug.category}</span>
                    </div>
                    <small style="color: #b0b0b0;">${new Date(sug.timestamp).toLocaleString()}</small>
                `;
                list.appendChild(item);
            });
        }

        // Close modals on outside click
        window.addEventListener('click', (e) => {
            const authModal = document.getElementById('authModal');
            const trackingModal = document.getElementById('trackingModal');
            
            if (e.target === authModal) {
                closeAuthModal();
            }
            if (e.target === trackingModal) {
                closeTrackingModal();
            }
        });