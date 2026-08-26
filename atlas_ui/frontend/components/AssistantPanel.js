export function renderAssistantPanel(container, token) {
    const panel = document.createElement("div");
    panel.id = "assistant-panel";
    panel.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 350px;
        height: 500px;
        background: rgba(15, 20, 25, 0.95);
        border: 1px solid rgba(0, 255, 128, 0.3);
        border-radius: 12px;
        display: flex;
        flex-direction: column;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        backdrop-filter: blur(10px);
        z-index: 9999;
        overflow: hidden;
        transition: transform 0.3s ease;
    `;

    const header = document.createElement("div");
    header.style.cssText = `
        padding: 15px;
        background: rgba(0, 255, 128, 0.1);
        border-bottom: 1px solid rgba(0, 255, 128, 0.2);
        color: #00ff80;
        font-weight: 600;
        display: flex;
        justify-content: space-between;
        align-items: center;
        cursor: pointer;
    `;
    header.innerHTML = `
        <span>ATLAS Assistant</span>
        <span id="assistant-toggle" style="font-size: 1.2rem; cursor: pointer;">▼</span>
    `;

    const chatContainer = document.createElement("div");
    chatContainer.id = "assistant-chat-container";
    chatContainer.style.cssText = `
        flex: 1;
        padding: 15px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 10px;
        color: #eee;
    `;

    const inputContainer = document.createElement("div");
    inputContainer.style.cssText = `
        padding: 15px;
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        display: flex;
        gap: 10px;
    `;

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Ask ATLAS...";
    input.style.cssText = `
        flex: 1;
        padding: 10px;
        background: rgba(0,0,0,0.5);
        border: 1px solid rgba(255,255,255,0.2);
        border-radius: 6px;
        color: white;
        outline: none;
    `;

    const micBtn = document.createElement("button");
    micBtn.innerHTML = "🎤";
    micBtn.style.cssText = `
        padding: 10px;
        background: rgba(0, 255, 128, 0.1);
        border: 1px solid rgba(0, 255, 128, 0.3);
        color: #00ff80;
        border-radius: 6px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
    `;

    const sendBtn = document.createElement("button");
    sendBtn.innerText = "SEND";
    sendBtn.style.cssText = `
        padding: 10px 15px;
        background: rgba(0, 255, 128, 0.2);
        border: 1px solid #00ff80;
        color: #00ff80;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 600;
    `;

    inputContainer.appendChild(micBtn);
    inputContainer.appendChild(input);
    inputContainer.appendChild(sendBtn);
    
    panel.appendChild(header);
    panel.appendChild(chatContainer);
    panel.appendChild(inputContainer);
    container.appendChild(panel);

    // Toggle minimize
    let isMinimized = false;
    header.addEventListener("click", () => {
        isMinimized = !isMinimized;
        panel.style.transform = isMinimized ? "translateY(calc(100% - 53px))" : "translateY(0)";
        document.getElementById("assistant-toggle").innerText = isMinimized ? "▲" : "▼";
    });

    // Voice Support via Web Speech API (Voice Assistant v1)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let voiceState = "OFF"; // OFF, IDLE (waiting for wake word), LISTENING (wake word heard), PROCESSING (speaking/fetching)
    let shouldListen = false;
    
    // UI update helper
    const updateVoiceUI = () => {
        if (voiceState === "OFF") {
            micBtn.style.background = "rgba(0, 255, 128, 0.1)";
            micBtn.style.borderColor = "rgba(0, 255, 128, 0.3)";
            micBtn.style.boxShadow = "none";
            input.placeholder = "Ask ATLAS...";
        } else if (voiceState === "IDLE") {
            micBtn.style.background = "rgba(0, 150, 255, 0.2)";
            micBtn.style.borderColor = "#0096ff";
            micBtn.style.boxShadow = "none";
            input.placeholder = "Waiting for 'ATLAS'...";
        } else if (voiceState === "LISTENING") {
            micBtn.style.background = "rgba(255, 0, 0, 0.2)";
            micBtn.style.borderColor = "red";
            micBtn.style.boxShadow = "0 0 10px red";
            input.placeholder = "Listening...";
        } else if (voiceState === "PROCESSING") {
            micBtn.style.background = "rgba(255, 165, 0, 0.2)";
            micBtn.style.borderColor = "orange";
            micBtn.style.boxShadow = "none";
            input.placeholder = "Processing...";
        }
    };

    // TTS Helper
    window.atlasSpeak = (text) => {
        if ('speechSynthesis' in window) {
            // Stop listening to prevent feedback
            if (recognition && voiceState !== "OFF") {
                recognition.stop(); 
            }
            const prevState = voiceState;
            voiceState = "PROCESSING";
            updateVoiceUI();
            
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.onend = () => {
                if (prevState !== "OFF") {
                    voiceState = "IDLE";
                    updateVoiceUI();
                    if (shouldListen) {
                        try { recognition.start(); } catch(e){}
                    }
                } else {
                    voiceState = "OFF";
                    updateVoiceUI();
                }
            };
            window.speechSynthesis.speak(utterance);
        }
    };

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        
        recognition.onstart = () => {
            if (voiceState === "OFF" || voiceState === "PROCESSING") {
                voiceState = "IDLE";
            }
            updateVoiceUI();
        };
        
        recognition.onresult = (event) => {
            if (voiceState === "OFF" || voiceState === "PROCESSING") return;
            
            // Get the latest result
            const current = event.resultIndex;
            const transcript = event.results[current][0].transcript.trim().toLowerCase();
            console.log("[Voice] Transcript:", transcript);
            
            if (voiceState === "IDLE") {
                // Check for wake word
                const wakeWords = ["atlas", "hey atlas", "okay atlas", "ok atlas"];
                let foundWakeWord = "";
                
                for (const w of wakeWords) {
                    if (transcript.includes(w)) {
                        foundWakeWord = w;
                        break;
                    }
                }
                
                if (foundWakeWord) {
                    const idx = transcript.indexOf(foundWakeWord);
                    const remainder = transcript.substring(idx + foundWakeWord.length).trim();
                    
                    if (remainder.length > 0) {
                        // Wake word + command in one breath
                        input.value = remainder;
                        voiceState = "PROCESSING";
                        updateVoiceUI();
                        sendMessage();
                    } else {
                        // Just wake word, enter LISTENING state
                        voiceState = "LISTENING";
                        updateVoiceUI();
                        // Optional: play a subtle beep here if desired
                    }
                }
            } else if (voiceState === "LISTENING") {
                // We were already waiting for a command
                if (transcript.length > 0) {
                    input.value = transcript;
                    voiceState = "PROCESSING";
                    updateVoiceUI();
                    sendMessage();
                }
            }
        };
        
        let restartTimeout = null;
        
        recognition.onerror = (event) => {
            console.error("Speech recognition error:", event.error);
            clearTimeout(restartTimeout);
            
            switch (event.error) {
                case 'not-allowed':
                case 'audio-capture':
                case 'service-not-allowed':
                    shouldListen = false;
                    voiceState = "OFF";
                    addMessage("system", "Microphone access denied or unavailable.");
                    break;
                case 'network':
                    // Temporary back-off retry
                    if (shouldListen) {
                        restartTimeout = setTimeout(() => {
                            if (shouldListen && voiceState !== "OFF" && voiceState !== "PROCESSING") {
                                try { recognition.start(); } catch(e){}
                            }
                        }, 2000);
                    }
                    break;
                case 'no-speech':
                case 'aborted':
                default:
                    // Will auto-restart in onend if shouldListen is true
                    break;
            }
            updateVoiceUI();
        };
        
        recognition.onend = () => {
            // Auto-restart if we are supposed to be listening and not explicitly OFF or PROCESSING (TTS speaking)
            if (shouldListen && voiceState !== "OFF" && voiceState !== "PROCESSING") {
                clearTimeout(restartTimeout);
                restartTimeout = setTimeout(() => {
                    if (shouldListen && voiceState !== "OFF" && voiceState !== "PROCESSING") {
                        try { 
                            recognition.start(); 
                        } catch (e) { 
                            console.error("Failed to restart recognition", e); 
                        }
                    }
                }, 500); // Slight delay to prevent aggressive infinite loop
            }
        };
    } else {
        micBtn.style.opacity = "0.5";
        micBtn.title = "Speech Recognition not supported in this browser.";
    }

    micBtn.addEventListener("click", () => {
        if (!recognition) return;
        if (shouldListen) {
            shouldListen = false;
            voiceState = "OFF";
            recognition.stop();
        } else {
            shouldListen = true;
            voiceState = "IDLE";
            try { recognition.start(); } catch(e){}
        }
        updateVoiceUI();
    });

    const addMessage = (role, text) => {
        const msg = document.createElement("div");
        const isUser = role === 'user';
        msg.style.cssText = `
            padding: 10px;
            border-radius: 8px;
            max-width: 85%;
            word-wrap: break-word;
            align-self: ${isUser ? 'flex-end' : 'flex-start'};
            background: ${isUser ? 'rgba(0, 255, 128, 0.15)' : 'rgba(255, 255, 255, 0.05)'};
            border: 1px solid ${isUser ? 'rgba(0, 255, 128, 0.3)' : 'rgba(255, 255, 255, 0.1)'};
            color: ${isUser ? '#00ff80' : '#ddd'};
        `;
        msg.innerText = text;
        chatContainer.appendChild(msg);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    };

    // WebSocket Connection
    let ws = null;
    const connectWebSocket = () => {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/events`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("[ATLAS Assistant] WebSocket connected.");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "agent_status") {
                    if (data.status === "THINKING") {
                        addMessage("assistant", "..."); // Simple thinking indicator
                    } else if (data.status === "INTENT_DETECTED") {
                        const msgs = chatContainer.querySelectorAll("div");
                        if (msgs.length > 0 && msgs[msgs.length - 1].innerText === "...") {
                            msgs[msgs.length - 1].innerText = `[INTENT DETECTED: ${data.intent}]`;
                        }
                    } else if (data.status === "EXECUTING") {
                        const msgs = chatContainer.querySelectorAll("div");
                        if (msgs.length > 0 && msgs[msgs.length - 1].innerText.includes("[INTENT DETECTED")) {
                            msgs[msgs.length - 1].innerText = `[EXECUTING: ${data.message}]`;
                        }
                    } else if (data.status === "COMPLETED" || data.status === "FAILED") {
                        // The REST API call will also return this, but we can handle live updates here
                        console.log(`[ATLAS Assistant] Reasoning ${data.status} via WS`, data.result);
                    }
                } else if (data.type === "vision_event") {
                    addMessage("system", `[VISION EVENT] ${data.event_type}`);
                } else if (data.type === "system_alert") {
                    addMessage("system", `[ALERT] ${data.message}`);
                }
            } catch (err) {
                console.error("[ATLAS Assistant] Error parsing WS message:", err);
            }
        };

        ws.onclose = () => {
            console.log("[ATLAS Assistant] WebSocket disconnected. Reconnecting in 5s...");
            setTimeout(connectWebSocket, 5000);
        };
    };

    connectWebSocket();

    const sendMessage = async () => {
        const text = input.value.trim();
        if (!text) return;
        
        input.value = "";
        addMessage("user", text);

        try {
            const res = await fetch("/api/v1/assistant/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ message: text })
            });
            const data = await res.json();
            
            if (!res.ok) {
                addMessage("assistant", "Error: " + (data.error || "Failed to process request"));
                return;
            }

            // Remove thinking indicator if present
            const msgs = chatContainer.querySelectorAll("div");
            if (msgs.length > 0) {
                const lastText = msgs[msgs.length - 1].innerText;
                if (lastText === "..." || lastText.includes("[INTENT DETECTED") || lastText.includes("[EXECUTING")) {
                    chatContainer.removeChild(msgs[msgs.length - 1]);
                }
            }
            
            // Escape HTML helper
            const escapeHtml = (unsafe) => {
                return (unsafe || "").toString()
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#039;");
            };

            // Format Response
            let responseHtml = "";
            if (data.status === "completed") {
                if (data.type === "conversation") {
                    responseHtml += `<div style="margin-bottom: 10px; color: #a5d6ff;">${escapeHtml(data.message)}</div>`;
                } else {
                    responseHtml += `<div style="color: #00ff80; font-weight: bold; margin-bottom: 5px;">✓ ${data.intent || "ACTION COMPLETED"}</div>`;
                    responseHtml += `<div style="margin-bottom: 10px;">${escapeHtml(data.message)}</div>`;
                }
            } else if (data.status === "rejected") {
                responseHtml += `<div style="color: #ff4444; font-weight: bold; margin-bottom: 5px;">✗ ACTION REJECTED</div>`;
                responseHtml += `<div>${escapeHtml(data.message)}</div>`;
            } else if (data.status === "unsupported") {
                responseHtml += `<div style="color: #ffaa00; font-weight: bold; margin-bottom: 5px;">⚠ UNSUPPORTED</div>`;
                responseHtml += `<div>${escapeHtml(data.message)}</div>`;
            } else if (data.status === "failed") {
                responseHtml += `<div style="color: #ff4444; font-weight: bold; margin-bottom: 5px;">✗ ACTION FAILED</div>`;
                responseHtml += `<div>${escapeHtml(data.message)}</div>`;
            } else {
                responseHtml += `<div>${escapeHtml(data.message || "Unknown response status.")}</div>`;
            }
            
            // Render technical output safely if it exists
            if (data.execution && (data.execution.stdout || data.execution.stderr)) {
                const uniqueId = "exec-" + Math.random().toString(36).substr(2, 9);
                const techOut = (data.execution.stdout || "") + (data.execution.stderr ? "\n" + data.execution.stderr : "");
                responseHtml += `
                    <div style="margin-top: 10px; font-size: 0.9em;">
                        <div style="cursor: pointer; color: #aaa; border-bottom: 1px solid #444; padding-bottom: 3px;" onclick="document.getElementById('${uniqueId}').style.display = document.getElementById('${uniqueId}').style.display === 'none' ? 'block' : 'none'">
                            ▶ View technical output
                        </div>
                        <pre id="${uniqueId}" style="display: none; background: rgba(0,0,0,0.5); padding: 10px; border-radius: 4px; overflow-x: auto; font-family: monospace; color: #ccc; margin-top: 5px;">${escapeHtml(techOut)}</pre>
                    </div>
                `;
            }

            // addMessage needs to support innerHTML for the response, let's create a custom message element for assistant
            const msg = document.createElement("div");
            msg.style.cssText = `
                padding: 10px;
                border-radius: 8px;
                max-width: 85%;
                word-wrap: break-word;
                align-self: flex-start;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #ddd;
            `;
            msg.innerHTML = responseHtml;
            chatContainer.appendChild(msg);
            chatContainer.scrollTop = chatContainer.scrollHeight;

            if (window.atlasSpeak && data.message) {
                window.atlasSpeak(data.message);
            }

        } catch (err) {
            // Remove thinking indicator if present
            const msgs = chatContainer.querySelectorAll("div");
            if (msgs.length > 0 && msgs[msgs.length - 1].innerText === "...") {
                chatContainer.removeChild(msgs[msgs.length - 1]);
            }
            addMessage("assistant", "Network Error: " + err.message);
        }
    };

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") sendMessage();
    });

    // Initial greeting
    addMessage("assistant", "ATLAS OS Assistant initialized. How can I help you?");
}
