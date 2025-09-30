// WebSocket connection handling
let ws;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 3000; // 3 seconds
function connectWebSocket() {
    try {
    // Always use ws:// for local development
    const protocol = 'ws://';
    // Get the current host
    // Function to get the correct path for an image
    function getImagePath(filename) {
        const staticPath = '/static/';
        // If the filename already has the static path, return it as is
        if (filename.startsWith(staticPath) || filename.startsWith('/static/')) {
            return filename;
        }
        // Otherwise, prepend the static path
        return staticPath + filename;
    }

    // Track selected agent profile
    window.selectedAgent = {
        name: null,
        img: getImagePath('unknown.jpg'),
        class: 'unknown'
    };

    // Listen for agent selection from HTML (index.html calls this)
    window.setAgentProfile = function(name) {
        const agents = {
            'Erica': { img: getImagePath('gambar1.jpg'), class: 'erica' },
            'Leo': { img: getImagePath('gambar2.jpg'), class: 'leo' },
            'Damia': { img: getImagePath('gambar3.jpg'), class: 'damia' },
            'Unknown': { img: getImagePath('unknown.jpg'), class: 'unknown' }
        };
        const agent = agents[name] || agents['Unknown'];
        window.selectedAgent = {
            name: name,
            img: agent.img,
            class: agent.class
        };
    };
    const host = window.location.hostname;
    // Use port 8000 for WebSocket to match backend
    const wsUrl = `${protocol}${host}:8000/ws`;
        console.log('Attempting to connect to WebSocket at', wsUrl);
        ws = new WebSocket(wsUrl);

        ws.onopen = function() {
            console.log('WebSocket connection established');
            reconnectAttempts = 0; // Reset reconnect attempts on successful connection
            // Show connection status
            const status = document.getElementById('connection-status');
            if (status) status.textContent = 'Connected';
        };

        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
        };

        ws.onclose = function(event) {
            console.log('WebSocket connection closed:', event.code, event.reason);
            
            // Show connection status
            const status = document.getElementById('connection-status') || (function() {
                const s = document.createElement('div');
                s.id = 'connection-status';
                s.style.position = 'fixed';
                s.style.bottom = '10px';
                s.style.right = '10px';
                s.style.padding = '5px 10px';
                s.style.background = '#ff4444';
                s.style.color = 'white';
                s.style.borderRadius = '4px';
                s.style.zIndex = '1000';
                document.body.appendChild(s);
                return s;
            })();
            
            // Only reconnect if the closure was not normal (code !== 1000)
            if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
                status.textContent = 'Reconnecting...';
                status.style.background = '#ffbb33';
                reconnectAttempts++;
                console.log(`Attempting to reconnect (${reconnectAttempts}/${maxReconnectAttempts})...`);
                setTimeout(connectWebSocket, reconnectDelay);
            } else {
                status.textContent = 'Disconnected. Please refresh the page.';
                status.style.background = '#ff4444';
                if (event.code !== 1000) {
                    alert('Connection lost. Please refresh the page to continue.');
                }
            }
        };

        // Track message history to prevent duplicates
        const messageHistory = [];
        
        // Handle incoming messages
        ws.onmessage = async function(event) {
            console.log('Raw message received:', event.data);
            
            let msg;
            try {
                msg = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
                console.log('Parsed message object:', JSON.stringify(msg, null, 2));
                
                // Debug log the message type and content
                console.log('Message type:', msg.type || 'text');
                console.log('Message content:', msg.content || msg.text || msg.message || '(no content)');
                
                if (msg.buttons) {
                    console.log('Message contains buttons:', msg.buttons);
                } else {
                    console.log('Message does NOT contain buttons');
                }
            } catch (e) {
                console.error('Error parsing message:', e);
                // Create a basic message object if parsing fails
                msg = { content: String(event.data) };
            }
            
            const chatbox = document.getElementById('chatbox');
            
            // Remove any existing typing indicators
            const existingTyping = document.getElementById('typing');
            if (existingTyping) {
                existingTyping.remove();
            }

            try {
                let msg;
                try {
                    msg = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
                } catch (e) {
                    console.error('Error parsing message:', e);
                    msg = { content: String(event.data) };
                }
                
                console.log('Parsed message:', msg);
                
                // Get message content and type for duplicate checking
                const messageContent = msg.content || msg.message || msg.text || '';
                const messageType = msg.type || '';
                
                // Skip duplicate checks for certain message types
                const skipDuplicateCheck = ['buttons', 'campaign', 'benefits'].includes(messageType);
                if (!skipDuplicateCheck) {
                    const isDuplicate = messageHistory.some(m => {
                        const sameContent = m.content === messageContent.trim();
                        const sameType = m.type === messageType;
                        const recent = (Date.now() - m.timestamp) < 1000; // 1 second threshold
                        return sameContent && sameType && recent;
                    });
                    
                    if (isDuplicate) {
                        console.log('Skipping duplicate message:', { type: messageType, content: messageContent });
                        return;
                    }
                }
                
                // Create a unique ID for this message
                const messageId = Date.now() + '-' + Math.random().toString(36).substr(2, 9);
                
                // Add to message history with unique ID
                const messageObj = {
                    id: messageId,
                    content: messageContent.trim(),
                    type: messageType,
                    timestamp: Date.now(),
                    raw: JSON.parse(JSON.stringify(msg)) // Store a copy of the raw message
                };
                messageHistory.unshift(messageObj);
                
                console.log('Added message to history:', {
                    id: messageId,
                    type: messageType,
                    content: messageContent.trim().substring(0, 50) + '...',
                    hasButtons: !!(msg.buttons && msg.buttons.length > 0)
                });
                
                // Keep only the most recent messages (last 10)
                while (messageHistory.length > 10) {
                    messageHistory.pop();
                }
                
                // Create container for the message
                const container = document.createElement('div');
                container.className = 'bot';
                // Get the selected agent's info or use defaults
                const defaultAgent = {
                    name: 'Unknown',
                    class: 'unknown',
                    img: getImagePath('unknown.jpg')
                };
                const agent = window.selectedAgent || defaultAgent;
                
                // Create container for profile and name
                const profileContainer = document.createElement('div');
                profileContainer.style.display = 'flex';
                profileContainer.style.alignItems = 'center';
                
                // Create profile picture
                const profilePic = document.createElement('span');
                profilePic.className = `profile-pic ${agent.class || 'unknown'}`;
                profilePic.style.backgroundImage = `url('${agent.img}')`;
                profilePic.title = agent.name || 'Unknown Agent';
                
                // Add agent name next to profile
                const nameSpan = document.createElement('span');
                nameSpan.textContent = agent.name || '';
                nameSpan.style.marginLeft = '8px';
                nameSpan.style.fontWeight = 'bold';
                
                // Add elements to container
                profileContainer.appendChild(profilePic);
                profileContainer.appendChild(nameSpan);
                container.appendChild(profileContainer);
                // Debug: Log message type and content
                console.log('Message type:', msg.type || 'regular message');
                console.log('Message content:', messageContent);
                
                // Handle error messages first
                if (msg.type === 'error') {
                    // If reset flag is set, clear the chat first
                    if (msg.reset) {
                        const chatbox = document.getElementById('chatbox');
                        chatbox.innerHTML = ''; // Clear all messages
                    }
                    
                    // Only add error if it's not a duplicate of the last message
                    const lastMessage = chatbox.lastElementChild;
                    if (!lastMessage || !lastMessage.classList.contains('error') || 
                        lastMessage.textContent !== msg.content) {
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'error';
                        errorDiv.textContent = msg.content;
                        container.appendChild(errorDiv);
                    }
                }
                // Handle button messages - check for buttons array first
                if (msg.buttons && Array.isArray(msg.buttons)) {
                    console.log('Processing button message:', {
                        type: msg.type,
                        hasContent: !!(msg.content || msg.text || msg.message),
                        buttonCount: msg.buttons ? msg.buttons.length : 0,
                        nextStep: msg.next_step,
                        rawMessage: msg
                    });
                    
                    // Show the message content if it exists
                    if (msg.content || msg.text || msg.message) {
                        const textDiv = document.createElement('div');
                        // Use message content in order of preference: content -> text -> message
                        const messageText = msg.content || msg.text || msg.message;
                        // Convert markdown-style formatting to HTML
                        let formattedContent = messageText
                            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Bold: **text**
                            .replace(/\*(.*?)\*/g, '<em>$1</em>')              // Italic: *text*
                            .replace(/\n/g, '<br>')                              // Newlines
                            .replace(/•/g, '•');                             // Bullet points
                        
                        textDiv.innerHTML = formattedContent;
                        container.appendChild(textDiv);
                        
                        // Log the rendered content for debugging
                        console.log('Rendered message content:', formattedContent);
                    }
                    
                    // Add buttons if present
                    if (msg.buttons && msg.buttons.length > 0) {
                        console.log('Adding buttons:', msg.buttons);
                        const buttonContainer = document.createElement('div');
                        buttonContainer.className = 'button-group';
                        console.log('Button container created:', buttonContainer);
                        
                        msg.buttons.forEach((btn) => {
                            const button = document.createElement('button');
                            button.className = 'chat-button btn';
                            button.textContent = btn.label || btn;
                            
                            // Set button value if available
                            if (btn.value) {
                                button.value = btn.value;
                                button.dataset.value = btn.value;
                            }
                            
                            // Add click handler
                            button.onclick = async function(e) {
                                e.stopPropagation();
                                
                                // Get the value and label from the button
                                const value = btn.value || btn.label || btn;
                                const label = btn.label || btn;
                                
                                console.log('Button clicked - Value:', value, 'Label:', label);
                                
                                // Disable all buttons in this group to prevent multiple clicks
                                const buttons = buttonContainer.querySelectorAll('button');
                                buttons.forEach(btn => {
                                    btn.disabled = true;
                                    btn.style.opacity = '0.7';
                                    btn.style.cursor = 'not-allowed';
                                });
                                
                                // Create a message indicating the user's choice
                                const choiceMessage = document.createElement('div');
                                choiceMessage.className = 'user-choice';
                                choiceMessage.textContent = `You selected: ${label}`;
                                container.appendChild(choiceMessage);
                                
                                // Scroll to show the latest message
                                chatbox.scrollTop = chatbox.scrollHeight;
                                
                                // Prepare the message to send to the server
                                const message = {
                                    type: 'choice',
                                    value: value,
                                    label: label,
                                    timestamp: Date.now()
                                };
                                
                                console.log('Sending message to server:', message);
                                
                                try {
                                    // Send the message to the server
                                    ws.send(JSON.stringify(message));
                                    console.log('Message sent successfully');
                                } catch (error) {
                                    console.error('Error sending message:', error);
                                    // Re-enable buttons if there was an error
                                    buttons.forEach(btn => {
                                        btn.disabled = false;
                                        btn.style.opacity = '1';
                                        btn.style.cursor = 'pointer';
                                    });
                                }
                            };
                            
                            buttonContainer.appendChild(button);
                        });
                        console.log('Appending button container to message container:', buttonContainer);
                        container.appendChild(buttonContainer);
                        console.log('Message container after appending buttons:', container);
                    }
                }
                // Handle campaign recommendations
                else if (msg.type === 'campaign') {
                    const campaignCard = document.createElement('div');
                    campaignCard.className = 'campaign-card';
                    
                    const title = document.createElement('h3');
                    title.textContent = msg.title || 'Campaign';
                    campaignCard.appendChild(title);
                    
                    if (msg.description) {
                        const desc = document.createElement('p');
                        desc.textContent = msg.description;
                        campaignCard.appendChild(desc);
                    }
                    
                    // Add a button to learn more about the campaign
                    const learnMoreBtn = document.createElement('button');
                    learnMoreBtn.className = 'campaign-button';
                    learnMoreBtn.textContent = 'Learn More';
                    learnMoreBtn.onclick = () => {
                        // You can add more detailed campaign view or navigation here
                        alert(`More information about ${msg.title} will be shown here.`);
                    };
                    campaignCard.appendChild(learnMoreBtn);
                    
                    container.appendChild(campaignCard);
                } else if (msg.type !== 'buttons') {
                    // Handle regular text messages
                    const textDiv = document.createElement('div');
                    const content = msg.content || msg.message || msg.text || event.data;
                    
                    // Simple markdown parsing for bold text and line breaks
                    let formattedContent = content
                        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // **bold**
                        .replace(/\*(.*?)\*/g, '<em>$1</em>')                // *italic*
                        .replace(/\n/g, '<br>');                              // new lines
                    
                    textDiv.innerHTML = formattedContent;
                    container.appendChild(textDiv);
                }
                
                // Add the message to the chatbox
                console.log('Final container before adding to chat:', container);
                if (container.childNodes.length > 0) {
                    console.log('Adding container to chatbox:', container);
                    chatbox.appendChild(container);
                    chatbox.scrollTop = chatbox.scrollHeight;
                    console.log('Chatbox after adding container:', chatbox);
                } else {
                    console.warn('Container is empty, not adding to chatbox');
                }

                // Show typing indicator if there are more messages coming
                if (msg.is_typing) {
                    setTimeout(() => {
                        const typing = document.createElement('div');
                        typing.className = 'typing';
                        typing.id = 'typing';
                        typing.innerHTML = '<span></span><span></span><span></span>';
                        chatbox.appendChild(typing);
                        chatbox.scrollTop = chatbox.scrollHeight;
                    }, 500);
                }
                
            } catch (error) {
                console.error('Error processing message:', error);
                // Fallback: display the raw message if parsing fails
                const container = document.createElement('div');
                container.className = 'bot error';
                container.textContent = 'Error: Could not process message';
                chatbox.appendChild(container);
                chatbox.scrollTop = chatbox.scrollHeight;
            }
        };
        
    } catch (error) {
        console.error('Error creating WebSocket:', error);
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            console.log(`Retrying connection (${reconnectAttempts}/${maxReconnectAttempts})...`);
            setTimeout(connectWebSocket, reconnectDelay);
        }
    }
}

// Initial connection
connectWebSocket();

function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (message === '') return;

    // Check if WebSocket is connected
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.error('WebSocket is not connected');
        alert('Not connected to server. Please refresh the page.');
        return;
    }

    // Add user message to chat with profile
    const chatbox = document.getElementById('chatbox');
    const userContainer = document.createElement('div');
    userContainer.className = 'user';
    // Profile span for user
    const userProfileSpan = document.createElement('span');
    userProfileSpan.className = 'user-profile you';
        userProfileSpan.innerHTML = `
            <img src='/static/you.png' alt='You' style='width:28px;height:28px;border-radius:50%;object-fit:cover;vertical-align:middle;'>
            <span style='color:black;font-weight:bold;font-size:0.95em;margin-left:6px;vertical-align:middle;'>You</span>
        `;
    userContainer.appendChild(userProfileSpan);
    // Message text
    const userTextDiv = document.createElement('div');
    userTextDiv.className = 'user-text';
    userTextDiv.textContent = message;
    userContainer.appendChild(userTextDiv);
    chatbox.appendChild(userContainer);
    chatbox.scrollTop = chatbox.scrollHeight;

    // Clear input
    input.value = '';

    // Send message to server
    ws.send(JSON.stringify({ text: message }));
}

// Track active button submissions to prevent duplicates
const activeButtonSubmissions = new Set();

function sendChoice(value, label) {
    // Create a unique identifier for this button click
    const clickId = `${value}-${Date.now()}`;
    
    // Check if we're already processing this button click
    if (activeButtonSubmissions.has(clickId)) {
        console.log('Already processing this button click, ignoring duplicate');
        return;
    }
    
    // Add to active submissions
    activeButtonSubmissions.add(clickId);
    
    try {
        // Add user's choice to chat
        const chatbox = document.getElementById('chatbox');
        const userChoice = document.createElement('div');
        userChoice.className = 'user';
        userChoice.textContent = label;
        chatbox.appendChild(userChoice);
        chatbox.scrollTop = chatbox.scrollHeight;
        
        // Disable all buttons to prevent multiple clicks
        const buttons = document.querySelectorAll('.btn');
        buttons.forEach(btn => {
            btn.disabled = true;
            btn.style.opacity = '0.7';
            btn.style.cursor = 'not-allowed';
        });
        
        // Send structured message to server
        if (ws && ws.readyState === WebSocket.OPEN) {
            const message = {
                type: 'choice',
                value: value,
                label: label,
                timestamp: Date.now()
            };
            ws.send(JSON.stringify(message));
            console.log('Sent choice to server:', message);
            
            // Re-enable buttons after a short delay
            setTimeout(() => {
                buttons.forEach(btn => {
                    btn.disabled = false;
                    btn.style.opacity = '1';
                    btn.style.cursor = 'pointer';
                });
                // Remove from active submissions after a longer delay
                setTimeout(() => {
                    activeButtonSubmissions.delete(clickId);
                }, 1000);
            }, 1000);
        } else {
            console.error('WebSocket not connected, cannot send choice');
            // Re-enable buttons immediately if WS is not connected
            buttons.forEach(btn => {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
            });
            activeButtonSubmissions.delete(clickId);
        }
    } catch (error) {
        console.error('Error in sendChoice:', error);
        // Ensure we clean up on error
        activeButtonSubmissions.delete(clickId);
        
        // Re-enable all buttons on error
        const buttons = document.querySelectorAll('.btn');
        buttons.forEach(btn => {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        });
    }
}

// Wait for the DOM to be fully loaded before adding event listeners
document.addEventListener('DOMContentLoaded', function() {
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendBtn');
    
    if (messageInput && sendButton) {
        // Handle form submission (using the input's keypress event)
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
            }
        });

        // Handle send button click
        sendButton.addEventListener('click', function(e) {
            e.preventDefault();
            sendMessage();
        });
    } else {
        console.error('Could not find required elements in the DOM');
    }
});
