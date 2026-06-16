/**
 * Playwright Automation Test Tool - Frontend Application
 * Handles form submission, file upload, SSE live log, OTP input, and phase progress.
 */

(function () {
    'use strict';

    // ---------------------------------------------------------------------------
    // State
    // ---------------------------------------------------------------------------

    let currentSessionId = null;
    let eventSource = null;

    // ---------------------------------------------------------------------------
    // DOM Elements
    // ---------------------------------------------------------------------------

    const testForm = document.getElementById('testForm');
    const startBtn = document.getElementById('startBtn');
    const fileUpload = document.getElementById('fileUpload');
    const fileLabel = document.getElementById('fileLabel');

    const phaseSection = document.getElementById('phaseSection');
    const otpSection = document.getElementById('otpSection');
    const otpInput = document.getElementById('otpInput');
    const otpSubmitBtn = document.getElementById('otpSubmitBtn');

    const logSection = document.getElementById('logSection');
    const logContainer = document.getElementById('logContainer');
    const logContent = document.getElementById('logContent');

    const resultsSection = document.getElementById('resultsSection');
    const reportLink = document.getElementById('reportLink');
    const reportDownload = document.getElementById('reportDownload');
    const scriptDownload = document.getElementById('scriptDownload');

    // ---------------------------------------------------------------------------
    // Utility Functions
    // ---------------------------------------------------------------------------

    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0;
            var v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    function classifyLogLine(message) {
        if (message.indexOf('[ERROR]') !== -1) return 'log-error';
        if (message.indexOf('=== Phase') !== -1 || message.indexOf('===') !== -1) return 'log-phase';
        if (message.indexOf('[Config]') !== -1) return 'log-config';
        if (message.indexOf('[Phase 3 - AI]') !== -1) return 'log-ai';
        return '';
    }

    function appendLog(message) {
        var line = document.createElement('span');
        line.className = 'log-line ' + classifyLogLine(message);
        line.textContent = message;
        logContent.appendChild(line);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function showSection(el) {
        el.style.display = '';
    }

    function hideSection(el) {
        el.style.display = 'none';
    }

    function setPhaseStatus(phaseNum, status) {
        var el = document.getElementById('phase' + phaseNum);
        var statusEl = document.getElementById('phase' + phaseNum + 'Status');
        if (el) {
            el.setAttribute('data-status', status);
        }
        if (statusEl) {
            statusEl.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }
    }

    function disableForm() {
        startBtn.disabled = true;
        startBtn.innerHTML = '<span class="btn-icon">&#9203;</span> Running...';
        var inputs = testForm.querySelectorAll('input');
        for (var i = 0; i < inputs.length; i++) {
            inputs[i].disabled = true;
        }
    }

    function enableForm() {
        startBtn.disabled = false;
        startBtn.innerHTML = '<span class="btn-icon">&#9654;</span> Start Test';
        var inputs = testForm.querySelectorAll('input');
        for (var i = 0; i < inputs.length; i++) {
            inputs[i].disabled = false;
        }
    }

    function resetUI() {
        logContent.innerHTML = '';
        hideSection(otpSection);
        hideSection(resultsSection);
        setPhaseStatus(1, 'pending');
        setPhaseStatus(2, 'pending');
        setPhaseStatus(3, 'pending');
    }

    function showError(message) {
        appendLog('[ERROR] ' + message);
    }

    // ---------------------------------------------------------------------------
    // File Upload Label
    // ---------------------------------------------------------------------------

    fileUpload.addEventListener('change', function () {
        if (fileUpload.files.length > 0) {
            fileLabel.textContent = fileUpload.files[0].name;
        } else {
            fileLabel.textContent = 'Choose .xlsx file or drag here';
        }
    });

    // ---------------------------------------------------------------------------
    // Upload File
    // ---------------------------------------------------------------------------

    function uploadFile(sessionId) {
        return new Promise(function (resolve, reject) {
            if (!fileUpload.files || fileUpload.files.length === 0) {
                resolve(null);
                return;
            }

            var formData = new FormData();
            formData.append('sessionId', sessionId);
            formData.append('file', fileUpload.files[0]);

            fetch('/api/upload', {
                method: 'POST',
                body: formData
            })
                .then(function (response) {
                    if (!response.ok) {
                        return response.json().then(function (data) {
                            throw new Error(data.error || 'Upload failed');
                        });
                    }
                    return response.json();
                })
                .then(function (data) {
                    appendLog('[Upload] File uploaded: ' + (data.filename || 'unknown') + ' (' + data.size + ' bytes)');
                    resolve(data);
                })
                .catch(function (err) {
                    reject(err);
                });
        });
    }

    // ---------------------------------------------------------------------------
    // Start Test
    // ---------------------------------------------------------------------------

    function startTest(sessionId, config) {
        return fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        })
            .then(function (response) {
                if (!response.ok) {
                    return response.json().then(function (data) {
                        throw new Error(data.error || 'Failed to start test');
                    });
                }
                return response.json();
            })
            .then(function (data) {
                return data.sessionId;
            });
    }

    // ---------------------------------------------------------------------------
    // SSE Connection
    // ---------------------------------------------------------------------------

    function connectSSE(sessionId) {
        if (eventSource) {
            eventSource.close();
        }

        var url = '/api/status/' + sessionId;
        eventSource = new EventSource(url);

        eventSource.onmessage = function (event) {
            try {
                var data = JSON.parse(event.data);
                handleSSEMessage(data);
            } catch (e) {
                appendLog(event.data);
            }
        };

        eventSource.addEventListener('complete', function (event) {
            try {
                var data = JSON.parse(event.data);
                handleCompletion(sessionId);
            } catch (e) {
                handleCompletion(sessionId);
            }
            eventSource.close();
            eventSource = null;
        });

        eventSource.onerror = function () {
            if (eventSource && eventSource.readyState === EventSource.CLOSED) {
                appendLog('[Connection] Stream closed');
                eventSource = null;
            }
        };
    }

    // ---------------------------------------------------------------------------
    // SSE Message Handling
    // ---------------------------------------------------------------------------

    function handleSSEMessage(data) {
        if (!data) return;

        var message = data.message || '';

        if (data.type === 'otp_required') {
            showSection(otpSection);
            otpInput.focus();
            appendLog('[OTP] OTP required - please enter it below');
            return;
        }

        if (data.type === 'log' && message) {
            appendLog(message);
            detectPhaseFromLog(message);
        }
    }

    function detectPhaseFromLog(message) {
        if (message.indexOf('=== Phase 1:') !== -1) {
            setPhaseStatus(1, 'running');
        } else if (message.indexOf('[Phase 1] Complete') !== -1) {
            setPhaseStatus(1, 'passed');
        } else if (message.indexOf('=== Phase 2:') !== -1) {
            setPhaseStatus(1, 'passed');
            setPhaseStatus(2, 'running');
        } else if (message.indexOf('[Phase 2] Complete') !== -1) {
            setPhaseStatus(2, 'passed');
        } else if (message.indexOf('=== Phase 3:') !== -1) {
            setPhaseStatus(2, 'passed');
            setPhaseStatus(3, 'running');
        } else if (message.indexOf('[Phase 3]') !== -1 && message.indexOf('Confidence') !== -1) {
            setPhaseStatus(3, 'passed');
        } else if (message.indexOf('[ERROR]') !== -1) {
            // Mark current running phase as failed
            for (var i = 1; i <= 3; i++) {
                var el = document.getElementById('phase' + i);
                if (el && el.getAttribute('data-status') === 'running') {
                    setPhaseStatus(i, 'failed');
                }
            }
        } else if (message.indexOf('[OTP] Waiting for OTP') !== -1) {
            showSection(otpSection);
            otpInput.focus();
        }
    }

    function handleCompletion(sessionId) {
        appendLog('\n[Done] Test session complete. Report is ready.');
        setPhaseStatus(3, 'passed');
        enableForm();

        // Show results with download links
        var reportUrl = '/api/report/' + sessionId;
        var reportDownloadUrl = '/api/download/report/' + sessionId;
        var scriptDownloadUrl = '/api/download/script/' + sessionId;

        reportLink.href = reportUrl;
        reportDownload.href = reportDownloadUrl;
        scriptDownload.href = scriptDownloadUrl;
        showSection(resultsSection);
    }

    // ---------------------------------------------------------------------------
    // OTP Submit
    // ---------------------------------------------------------------------------

    function submitOTP() {
        var otp = otpInput.value.trim();
        if (!otp) {
            otpInput.focus();
            return;
        }
        if (!currentSessionId) {
            showError('No active session');
            return;
        }

        fetch('/api/otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sessionId: currentSessionId,
                otp: otp
            })
        })
            .then(function (response) {
                if (!response.ok) {
                    return response.json().then(function (data) {
                        throw new Error(data.error || 'OTP submission failed');
                    });
                }
                return response.json();
            })
            .then(function () {
                appendLog('[OTP] OTP submitted successfully');
                hideSection(otpSection);
                otpInput.value = '';
            })
            .catch(function (err) {
                showError('OTP error: ' + err.message);
            });
    }

    otpSubmitBtn.addEventListener('click', submitOTP);

    otpInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            submitOTP();
        }
    });

    // ---------------------------------------------------------------------------
    // Form Submission
    // ---------------------------------------------------------------------------

    testForm.addEventListener('submit', function (e) {
        e.preventDefault();

        var frontendUrl = document.getElementById('frontendUrl').value.trim();
        var username = document.getElementById('username').value.trim();
        var password = document.getElementById('password').value;
        var backendUrl = document.getElementById('backendUrl').value.trim();

        if (!frontendUrl || !username || !password) {
            alert('Please fill in all required fields.');
            return;
        }

        // Generate session ID
        var sessionId = generateUUID();
        currentSessionId = sessionId;

        // Reset and prepare UI
        resetUI();
        disableForm();
        showSection(phaseSection);
        showSection(logSection);

        appendLog('[Session] Starting test session: ' + sessionId);

        // Step 1: Upload file (if present)
        uploadFile(sessionId)
            .then(function () {
                // Step 2: Start test
                var config = {
                    sessionId: sessionId,
                    frontendUrl: frontendUrl,
                    username: username,
                    password: password,
                    backendUrl: backendUrl
                };

                return startTest(sessionId, config);
            })
            .then(function (returnedSessionId) {
                // Step 3: Connect SSE
                currentSessionId = returnedSessionId;
                connectSSE(returnedSessionId);
            })
            .catch(function (err) {
                showError('Failed to start: ' + err.message);
                enableForm();
            });
    });

})();
