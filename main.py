# --- Required Imports ---
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from typing import Any
from Google_Sheet import append_row_to_sheet
import json
import logging
import time
import uuid

# --- Logger Setup ---
logger = logging.getLogger("chatbot")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# --- Conversation State ---
class ConversationState:
    def __init__(self):
        self.step: str = "get_name"  # Current step in the conversation flow
        self.user_data: dict[str, str] = {}  # User-specific data
        self.active_campaign: str | None = None  # Currently active campaign ID
        self.campaign_state: Any = None  # Campaign-specific state object

# --- Active Conversations ---
active_conversations = {}

# Message deduplication settings
MESSAGE_CACHE_TTL = 60  # 1 minute TTL for message cache
message_cache = {}  # Global message cache for deduplication

# Initialize message_cache in globals if not exists
if 'message_cache' not in globals():
    message_cache = {}

# --- Age Calculation Helper ---
def calculate_age(dob_str: str) -> str:
    try:
        dob = datetime.strptime(dob_str, "%d/%m/%Y")
        today = datetime.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return str(age)
    except Exception:
        return "Unknown"

app = FastAPI()
templates = Jinja2Templates(directory="templates")

import os

# Get the absolute path to the static directory
static_dir = os.path.join(os.path.dirname(__file__), 'static')

# Mount static files with absolute path
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    conv_id = str(uuid.uuid4())
    active_conversations[conv_id] = ConversationState()
    
    try:
        # Initialize conversation state
        state = active_conversations[conv_id]
        state.step = "get_name"
        
        # Don't send welcome message here - it's already shown in the HTML
        # Start conversation handler
        await handle_websocket_connection(websocket, conv_id)
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": "An error occurred. Please refresh the page and try again."
            })
        except:
            pass
    finally:
        if conv_id in active_conversations:
            del active_conversations[conv_id]

async def send_text(ws: WebSocket, message: str, is_user: bool = False) -> None:
    """Send a text message through WebSocket with error handling and logging.
    
    Args:
        ws: WebSocket connection
        message: Message text to send
        is_user: Whether the message is from the user (for UI display)
        
    Raises:
        WebSocketDisconnect: If the connection is closed
    """
    if not message or not isinstance(message, str):
        logger.warning("Attempted to send empty or invalid message")
        return
        
    message = message.strip()
    if not message:
        return
        
    try:
        payload = {
            "type": "message",
            "content": message,
            "is_user": is_user,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
        logger.debug(f"Sent message to {id(ws)}: {message[:100]}{'...' if len(message) > 100 else ''}")
        
    except WebSocketDisconnect:
        logger.warning("WebSocket disconnected while sending message")
        raise
    except Exception as e:
        logger.error(f"Error sending WebSocket message: {str(e)}", exc_info=True)
        # Attempt to notify client of the error
        try:
            error_payload = {
                "type": "error",
                "content": "Message delivery failed. Please try again.",
                "is_user": False
            }
            await ws.send_text(json.dumps(error_payload, ensure_ascii=False))
        except:
            pass
        raise

async def send_buttons(ws: WebSocket, message: str, buttons: list[dict[str, str]]) -> None:
    """Send a message with interactive buttons through WebSocket.
    
    Args:
        ws: WebSocket connection
        message: Message text to display above buttons
        buttons: List of button dictionaries with 'label' and 'value' keys
    """
    try:
        message_data: dict[str, str | list[dict[str, str]]] = {
            "type": "buttons",
            "content": message,  # Changed from 'text' to 'content' to match frontend expectation
            "buttons": buttons,
            "message": message,  # Keep for backward compatibility
            "text": message,    # Keep for backward compatibility
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"Sending message with buttons: {json.dumps(message_data, indent=2)}")
        await ws.send_json(message_data)
    except Exception as e:
        logger.error(f"Error sending buttons: {e}")
        raise

async def send_question(ws: WebSocket, message: str, input_type: str = "text") -> None:
    """Send a question that expects a text or number input.
    
    Args:
        ws: WebSocket connection
        message: The question to ask
        input_type: Type of input expected ('text' or 'number')
    """
    try:
        await ws.send_json({
            "type": "question",
            "content": message,
            "input_type": input_type
        })
    except Exception as e:
        logger.error(f"Error sending question: {e}")
        raise

async def show_campaign_options(ws: WebSocket, state: ConversationState, show_all: bool = False) -> None:
    """Display campaign options to the user.
    
    Args:
        ws: WebSocket connection
        state: Current conversation state with user data
        show_all: If True, show all campaigns regardless of priority
    """
    try:
        # Get user data for personalized recommendations
        primary_concern = state.user_data.get("primary_concern", "")
        life_stage = state.user_data.get("life_stage", "")
        dependents = int(state.user_data.get("dependents", 0))
        
        # Define all available campaigns with their priority logic
        # Get user's age, defaulting to 0 if not set or invalid
        try:
            user_age = int(state.user_data.get("age", 0))
        except (ValueError, TypeError):
            user_age = 0
            
        all_campaigns = [
            {
                "id": "sgsa",  # Must match the module_name in campaign_configs
                "title": "Satu Gaji Satu Harapan",
                "description": "Income protection plan that ensures your family's financial stability",
                "priority": 1 if primary_concern in ["income_protection", "medical_expenses"] or dependents > 0 else 1  # Always show with priority 1
            },
            {
                "id": "tabung_warisan",
                "title": "Tabung Warisan",
                "description": "Legacy planning to secure your family's future",
                "priority": 1 if primary_concern in ["retirement", "savings"] or user_age >= 40 else 0
            },
            {
                "id": "tabung_perubatan",
                "title": "Tabung Perubatan",
                "description": "Comprehensive medical coverage for you and your family",
                "priority": 1 if primary_concern in ["medical_expenses", "health"] or dependents > 0 else 1  # Always show with priority 1
            },
            {
                "id": "masa_depan_anak_kita",
                "title": "Masa Depan Anak Kita",
                "description": "Education savings plan for your children's future",
                "priority": 1 if primary_concern == "education" or dependents > 0 else 0
            },
            {
                "id": "perlindungan_combo",
                "title": "Perlindungan Combo",
                "description": "Comprehensive protection plan covering multiple needs",
                "priority": 1 if primary_concern in ["comprehensive", "all_round"] or life_stage in ["family", "married"] else 0
            }
        ]
        
        # If show_all is True, set all campaigns to priority 1
        if show_all:
            for campaign in all_campaigns:
                campaign['priority'] = 1
        else:
            # Otherwise, ensure all campaigns have at least priority 1
            for campaign in all_campaigns:
                campaign['priority'] = max(1, campaign.get('priority', 0))
        
        # Sort campaigns by priority (highest first) and then by title
        all_campaigns.sort(key=lambda x: (-x['priority'], x['title']))
        
        # Prepare the campaign options as buttons
        buttons = []
        displayed_campaigns = []
        
        for i, campaign in enumerate(all_campaigns, 1):
            if campaign['priority'] > 0:  # Only show campaigns with priority > 0
                buttons.append({
                    "label": f"{i}. {campaign['title']}",
                    "value": str(i)
                })
                displayed_campaigns.append(campaign['id'])
        
        # ...removed Show Menu button...
        
        # Store the displayed campaigns in the state for reference
        state.user_data['displayed_campaigns'] = displayed_campaigns
        
        # Clear any previous campaign state
        state.active_campaign = None
        state.campaign_state = None
        
        # Log the displayed campaigns for debugging
        logger.info(f"Displayed campaigns: {displayed_campaigns}")
        logger.info(f"Displayed buttons: {buttons}")
        
        # Ensure we have buttons to display
        if not buttons:
            logger.error("No buttons to display!")
            await send_text(ws, "Sorry, there was an error loading the campaign options. Please try again.")
            return
            
        # Send the message with buttons
        try:
            logger.info(f"Sending buttons to client: {buttons}")
            await ws.send_json({
                "type": "message",
                "content": "Here are the available plans. Please select one:",
                "buttons": buttons,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.info("Successfully sent campaign options to client")
        except Exception as e:
            logger.error(f"Error sending campaign options: {str(e)}", exc_info=True)
            await send_text(ws, "Sorry, there was an error displaying the options. Please try again.")
        
    except Exception as e:
        logger.error(f"Error showing campaign options: {str(e)}", exc_info=True)
        await send_text(ws, "Sorry, there was an error displaying the options. Please try again.")

async def log_conversation_state(state: ConversationState, message: str = "") -> None:
    """Log the current conversation state for debugging.
    
    Args:
        state: The current conversation state
        message: Optional message to include in the log
    """
    logger.info(f"[Conversation State] {message}")
    logger.info(f"Current step: {state.step}")
    logger.info(f"User data: {json.dumps(state.user_data, indent=2, default=str)}")
    if state.active_campaign:
        logger.info(f"Active campaign: {state.active_campaign}")

async def handle_websocket_connection(ws: WebSocket, conv_id: str):
    """Handle WebSocket connection and route messages to the appropriate campaign handler.
    
    Args:
        ws: WebSocket connection
        conv_id: Unique conversation ID
    """
    if conv_id not in active_conversations:
        logger.error(f"No active conversation found for ID: {conv_id}")
        await ws.close(code=1008, reason="Invalid conversation ID")
        return
        
    state = active_conversations[conv_id]
    conversation_active = True
    
    # Initialize campaign handlers
    campaign_handlers = {}
    campaign_import_errors = []
    
    # Add current directory to Python path to ensure imports work
    import sys
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    # Define campaign modules with their directory, module name, and instance name
    campaign_configs = [
        ("Campaign1", "sgsa", "sgsa_campaign"), 
        ("Campaign2", "tabung_warisan", "tabung_warisan_campaign"),
        ("Campaign3", "masa_depan_anak_kita", "masa_depan_anak_kita_campaign"),
        ("Campaign4", "tabung_perubatan", "tabung_perubatan_campaign_instance"), 
        ("Campaign5", "perlindungan_combo", "perlindungan_combo_campaign")
    ]
    
    for dir_name, module_name, instance_name in campaign_configs:
        campaign_id = module_name
        try:
            # Debug: Print current working directory and path
            import os
            logger.debug(f"Current working directory: {os.getcwd()}")
            module_path = os.path.join(os.path.dirname(__file__), dir_name, f"{module_name}.py")
            logger.debug(f"Looking for module at: {module_path}")
            logger.debug(f"Module exists: {os.path.exists(module_path)}")
            
            # Try importing the module
            full_module_name = f"{dir_name}.{module_name}"
            logger.info(f"\n{'='*80}")
            logger.info(f"=== ATTEMPTING TO IMPORT: {full_module_name} ===")
            logger.info(f"Looking for instance: {instance_name}")
            
            # Debug: Check if module exists
            try:
                import importlib.util
                import sys
                
                # Log Python path for debugging
                logger.info(f"Python path: {sys.path}")
                
                # Try to find the module spec
                logger.info(f"Looking for module: {full_module_name}")
                module_spec = importlib.util.find_spec(full_module_name)
                
                if module_spec is None:
                    error_msg = f"Module {full_module_name} not found!"
                    logger.error(error_msg)
                    # Try to find the module file manually
                    module_path = os.path.join(os.path.dirname(__file__), dir_name, f"{module_name}.py")
                    logger.info(f"Checking if module exists at: {module_path}")
                    if os.path.exists(module_path):
                        logger.info(f"Module file exists at: {module_path}")
                        logger.info(f"File contents: {os.listdir(os.path.dirname(module_path))}")
                    else:
                        logger.error(f"Module file not found at: {module_path}")
                    raise ImportError(error_msg)
                    
                logger.info(f"Module found at: {module_spec.origin}")
                
                # Try to import the module directly
                logger.info(f"Attempting to import {full_module_name}...")
                module = importlib.import_module(full_module_name)
                logger.info(f"Successfully imported {full_module_name}")
                logger.info(f"Module attributes: {[attr for attr in dir(module) if not attr.startswith('_')]}")
                
                # Check if the instance exists in the module
                if not hasattr(module, instance_name):
                    error_msg = f"Instance '{instance_name}' not found in module {full_module_name}"
                    logger.error(error_msg)
                    logger.error(f"Available attributes: {[attr for attr in dir(module) if not attr.startswith('_')]}")
                    raise AttributeError(error_msg)
                
                logger.info(f"Found instance '{instance_name}' in module {full_module_name}")
                
            except Exception as e:
                logger.error(f"Error finding/importing module {full_module_name}: {str(e)}", exc_info=True)
                raise
            
            # Import the module
            module = __import__(full_module_name, fromlist=[instance_name])
            logger.info(f"Successfully imported module: {full_module_name}")
            
            # Debug: List all names in the module
            module_names = [name for name in dir(module) if not name.startswith('_')]
            logger.info(f"Available names in module: {module_names}")
            
            # Get the campaign instance
            campaign_instance = getattr(module, instance_name, None)
            logger.info(f"Got campaign instance: {campaign_instance}")
            
            if campaign_instance is not None:
                campaign_handlers[campaign_id] = campaign_instance
                logger.info(f"✅ SUCCESS: Registered campaign handler: {campaign_id}")
                logger.info(f"Handler type: {type(campaign_instance).__name__}")
                logger.info(f"Available methods: {[m for m in dir(campaign_instance) if not m.startswith('_')]}")
            else:
                error_msg = f"❌ FAILED: Could not find instance {instance_name} in {full_module_name}"
                logger.error(error_msg)
                campaign_import_errors.append(error_msg)
                
        except ImportError as e:
            error_msg = f"Could not import campaign {dir_name}.{module_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            campaign_import_errors.append(error_msg)
        except Exception as e:
            error_msg = f"Error initializing campaign {campaign_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            campaign_import_errors.append(error_msg)
    
    # Log any import errors
    if campaign_import_errors:
        logger.warning(f"Encountered {len(campaign_import_errors)} errors while importing campaigns:")
        for error in campaign_import_errors:
            logger.warning(f"- {error}")
    
    if not campaign_handlers:
        error_msg = "No campaign handlers were imported successfully"
        logger.error(error_msg)
        await ws.send_json({
            "type": "error",
            "content": f"System error: {error_msg}. Please check the server logs for details."
        })
        return
    
    # Initialize response variable
    response = None
    
    # Ensure campaign state is initialized
    if not hasattr(state, 'campaign_state'):
        state.campaign_state = None
    
    while conversation_active:
        try:
            # Reset response for each iteration
            response = None
            
            # Receive message from client
            data = await ws.receive_text()
            if not data:
                logger.warning(f"Received empty message from client {conv_id}")
                continue
                
            # Initialize message content
            message_content = ""
            
            # Parse JSON if needed (for structured messages)
            try:
                message_data = json.loads(data)
                message_type = message_data.get("type", "message")
                
                # Handle button clicks (type: 'choice')
                if message_type == 'choice':
                    # Get the value and label from the button click
                    button_value = message_data.get('value')
                    button_label = message_data.get('label', '')
                    message_content = str(button_value)  # Use the button value as the message content
                    logger.info(f"Processing button click - value: {button_value}, label: {button_label}")
                else:
                    # For regular text messages
                    message_content = str(message_data.get('text', data)).strip()
                    logger.info(f"Received text message: {message_content[:200]}")
                    
            except (json.JSONDecodeError, AttributeError) as e:
                # If JSON parsing fails, treat as plain text
                message_type = "message"
                message_content = data if isinstance(data, str) else str(data)
                logger.info(f"Received raw message: {message_content[:200]}")
            
            # Log the final message being processed
            if message_content:
                logger.info(f"Processing message from {conv_id} (type: {message_type}): {message_content[:200]}")
            else:
                logger.warning("No message content to process")
            
            # Process campaign messages if we're in a campaign
            if state.active_campaign and state.active_campaign in campaign_handlers:
                campaign_id = state.active_campaign
                campaign_instance = campaign_handlers[campaign_id]
                
                try:
                    logger.info(f"Processing message in campaign {campaign_id}: {message_content}")
                    
                    # Skip empty or whitespace messages
                    if not message_content or not message_content.strip():
                        logger.info("Skipping empty message")
                        continue
                    
                    # Process button clicks immediately without duplicate checking
                    is_button_click = isinstance(message_content, dict) and message_content.get('type') == 'choice'
                    current_time = time.time()
                    
                    # Debug logging for button clicks
                    if is_button_click:
                        logger.info(f"[DEBUG] Processing button click - value: {message_content.get('value')}, type: {type(message_content.get('value'))}")
                        # Skip deduplication for button clicks
                        logger.info("Skipping deduplication for button click")
                    else:
                        # Only check for duplicates for non-button messages and non-choice messages
                        if message_type != 'choice':
                            message_fingerprint = f"{conv_id}:{message_content.strip().lower()}"
                            logger.info(f"[DEBUG] Processing regular message: {message_fingerprint}")
                            
                            # Initialize message_cache if it doesn't exist
                            if 'message_cache' not in globals():
                                global message_cache
                                message_cache = {}
                            
                            # Check for duplicate messages
                            message_cache_key = f"{conv_id}_{message_content}"
                            if message_cache_key in message_cache:
                                logger.info(f"[DEBUG] Duplicate detected - Key: {message_cache_key}, Cache: {message_cache}")
                                logger.info(f"Skipping duplicate message: {message_content}")
                                continue
                                
                            # Add to cache
                            message_cache[message_cache_key] = current_time
                            message_cache[message_fingerprint] = current_time
                        
                        # Clean up old cache entries (older than TTL)
                        message_cache = {
                            k: v for k, v in message_cache.items() 
                            if time.time() - v < MESSAGE_CACHE_TTL
                            if current_time - v < MESSAGE_CACHE_TTL
                        }
                    
                    # Process the message through the campaign handler
                    result = None
                    try:
                        logger.info(f"\n{'='*80}")
                        logger.info(f"[DEBUG] Processing message in campaign: {campaign_id}")
                        logger.info(f"[DEBUG] Message content: {message_content} (type: {type(message_content)})")
                        logger.info(f"[DEBUG] Current state: {state.__dict__ if hasattr(state, '__dict__') else state}")
                        
                        # Log available methods in the campaign instance
                        logger.info(f"[DEBUG] Available methods in {campaign_id}: {[m for m in dir(campaign_instance) if not m.startswith('_')]}")
                        
                        # Log the exact method being called
                        logger.info(f"[DEBUG] Calling process_message on {campaign_id} with message: {message_content}")
                        
                        # Process the message - preserve the original message structure for button clicks
                        logger.info(f"[WS HANDLER] Raw message_content: {message_content} (type: {type(message_content)})")
                        
                        if isinstance(message_content, dict) and message_content.get('type') == 'choice':
                            # For button clicks, pass the full message object
                            logger.info(f"[WS HANDLER] ===== PROCESSING BUTTON CLICK =====")
                            logger.info(f"[WS HANDLER] Full message content: {json.dumps(message_content, default=str)}")
                            logger.info(f"[WS HANDLER] Campaign ID: {campaign_id}")
                            logger.info(f"[WS HANDLER] Current state: {getattr(state, '__dict__', state)}")
                            
                            # Ensure we have the required fields
                            if 'value' not in message_content:
                                logger.error("[WS HANDLER] Button click missing 'value' field")
                            else:
                                logger.info(f"[WS HANDLER] Button value: {message_content.get('value')} (type: {type(message_content.get('value'))})")
                            
                            if 'label' not in message_content:
                                logger.warning("[WS HANDLER] Button click missing 'label' field")
                            else:
                                logger.info(f"[WS HANDLER] Button label: {message_content.get('label')}")
                            
                            # Log the current campaign state before processing
                            logger.info(f"[WS HANDLER] Current campaign state before processing: {getattr(state, 'campaign_state', {}).__dict__ if hasattr(state, 'campaign_state') else 'No campaign state'}")
                            
                            # Process the button click
                            result = await campaign_instance.process_message(
                                user_id=conv_id,
                                message=message_content,  # Pass the full message object
                                ws=ws,
                                user_data=state.user_data  # Pass user data including age
                            )
                            
                            # Log the result and updated state
                            logger.info(f"[WS HANDLER] Process message result: {json.dumps({k: v for k, v in result.items() if k != 'campaign_data'}, default=str) if isinstance(result, dict) else result}")
                            logger.info(f"[WS HANDLER] Updated campaign state: {getattr(state, 'campaign_state', {}).__dict__ if hasattr(state, 'campaign_state') else 'No campaign state'}")
                            logger.info("[WS HANDLER] ===== END BUTTON CLICK PROCESSING =====")
                        else:
                            # For regular text messages, strip and pass as string
                            result = await campaign_instance.process_message(
                                user_id=conv_id,
                                message=message_content.strip() if isinstance(message_content, str) else message_content,
                                ws=ws,  # For backward compatibility
                                user_data=state.user_data  # Pass user data including age
                            )
                        
                        logger.info(f"[DEBUG] Process result: {result}")
                        logger.info(f"{'='*80}\n")
                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}", exc_info=True)
                        await ws.send_json({
                            "type": "error",
                            "content": "An error occurred while processing your message. Please try again.",
                            "is_user": False,
                            "timestamp": datetime.now().isoformat()
                        })
                        continue
                    
                    # Skip if no result or result is not a dictionary
                    if not result or not isinstance(result, dict):
                        logger.warning("No valid result from campaign handler")
                        continue
                    
                    # Log the raw result for debugging (excluding large data)
                    log_result = {k: v for k, v in result.items() if k != 'campaign_data'}
                    logger.info(f"Campaign handler result: {json.dumps(log_result, default=str, indent=2)}")
                    
                    # Update campaign state if provided
                    if 'campaign_state' in result:
                        state.campaign_state = result['campaign_state']
                        logger.info(f"Updated campaign state: {state.campaign_state}")
                    
                    # Skip if response was already sent by the handler
                    if result.get('response_sent', False):
                        logger.info("Response already sent by campaign handler")
                        continue
                    
                    # Get the message content, preferring 'content' over 'response' for consistency
                    content = result.get('content', result.get('response', ''))
                    
                    # Skip empty responses (e.g., when handling the initial welcome)
                    if not content and not result.get('buttons') and not result.get('type') == 'campaign_selection':
                        logger.info("Skipping empty response")
                        continue
                    

                    # Handle campaign reset to main menu (get_name)
                    if isinstance(result, dict) and result.get('type') == 'reset_to_main':
                        logger.info("[MAIN] Received reset_to_main from campaign. Resetting conversation to get_name.")
                        state.active_campaign = None
                        state.campaign_state = None
                        state.user_data = {}
                        state.step = "get_name"
                        # Prompt for name at main menu
                        await send_text(ws, "Welcome back to the main menu! What's your name?")
                        # Wait for next user input before continuing
                        continue

                    # Prepare the base response object
                    response_data = {
                        "type": result.get('type', 'message'),
                        "text": content,  # Frontend expects 'text' for the message
                        "content": content,  # Keep for backward compatibility
                        "is_user": False,
                        "timestamp": datetime.now().isoformat(),
                        "campaign_data": result.get('campaign_data', {})
                    }
                    
                    # Handle different response types
                    if result.get('type') == 'buttons' and 'buttons' in result:
                        # For button responses, ensure we have the correct format
                        buttons = result['buttons']
                        if buttons and all(isinstance(btn, dict) for btn in buttons):
                            response_data.update({
                                "type": "buttons",
                                "buttons": [
                                    {"label": str(btn.get('label', '')), "value": str(btn.get('value', ''))}
                                    for btn in buttons
                                    if btn.get('label') is not None and btn.get('value') is not None
                                ]
                            })
                                
                            # Log the buttons being sent
                            logger.info(f"Sending buttons: {response_data['buttons']}")
                    
                    # Send the response with buttons
                    await ws.send_json(response_data)
                    
                    if isinstance(result, dict):
                        reset_to = result.get('reset_to')
                        return_to_select = result.get ('return_to_campaign_select',False)

                        if reset_to == "financial_concern" or return_to_select:
                            logger.info(f"[MAIN]Resetting to {reset_to} from campaign {state.active_campaign}")

                            # === reset campaign state ===
                            state.active_campaign = None
                            state.campaign_state = None

                            #set step back to financial concern flow
                            state.step = "get_financial_concern"

                            # Send Confirmation message 
                            await send_text(ws, "Back to Financial Concern section. What's your biggest financial concern right now?")

                            #Show financial concern buttons
                            await send_buttons(
                                ws,
                                "What's your biggest financial concern right now?"
                            )
                            #show financial concern buttons
                            await send_buttons(
                                ws,
                                "What's your biggest financial concern right now?",
                                [
                                    {"label": "Protecting my family's income", "value": "income_protection"},
                                    {"label": "Covering medical expenses", "value": "medical_expenses"},
                                    {"label": "Saving for children's education", "value": "education"},
                                    {"label": "Building long-term wealth", "value": "wealth_building"},
                                    {"label": "Planning for retirement", "value": "retirement"}
                                ]
                            )

                            #update step to wait for response 
                            state.step = "get_financial_concern_response"
                            continue

                    # Handle campaign selection response
                    if result.get('type') == 'campaign_selection' or result.get('return_to_campaign_select'):
                        logger.info("Handling campaign selection response")
                        state.active_campaign = None
                        state.campaign_state = None
                        
                        # Prepare the campaign selection response
                        response_data = {
                            "type": "campaign_selection",
                            "text": "Returning to campaign selection...",
                            "content": "Returning to campaign selection...",
                            "is_user": False,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        # Log the final response data
                        logger.info(f"Sending response: {json.dumps({k: v for k, v in response_data.items() if k != 'campaign_data'}, default=str)}")
                        
                        # Send the complete response
                        await ws.send_text(json.dumps(response_data, default=str))
                except Exception as e:
                    logger.error(f"Error processing campaign message: {str(e)}", exc_info=True)
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "text": f"Error processing your request: {str(e)}",
                        "is_user": False
                    }))
                
                continue
            
            # Main conversation flow - only process if not in a campaign
            if not state.active_campaign and state.step == "get_name":
                name = message_content.strip()
                # Simple validation - just check if there's any text
                if not name.strip():
                    await send_text(ws, "Please enter your name.")
                    continue
                
                # Capitalize the name properly
                name = ' '.join(word.capitalize() for word in name.split())
                state.user_data["name"] = name
                await send_question(ws, "What is your date of birth? (DD/MM/YYYY)")
                state.step = "get_dob"
                
            elif state.step == "get_dob":
                import re
                dob = message_content.strip()
                # Validate date format DD/MM/YYYY
                if not re.match(r'^\d{2}/\d{2}/\d{4}$', dob):
                    await send_text(ws, "Please enter your date of birth in DD/MM/YYYY format:")
                    continue
                else:
                    try:
                        # Validate it's a real date
                        day, month, year = map(int, dob.split('/'))
                        datetime(year=year, month=month, day=day)  # Will raise ValueError if invalid
                        state.user_data["dob"] = dob
                        age = calculate_age(dob)
                        state.user_data["age"] = str(age)
                        await send_text(ws, f"You are {age} years old. Thank you!")
                        
                        # Ask for email
                        await send_question(ws, "What is your email address? (e.g., example@email.com)")
                        state.step = "get_email"
                    except (ValueError, IndexError):
                        await send_text(ws, "Please enter a valid date of birth (DD/MM/YYYY):")
                        continue
                        
            elif state.step == "get_email":
                import re
                email = message_content.strip().lower()
                # Basic email validation
                if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
                    await send_text(ws, "Please enter a valid email address (e.g., example@email.com):")
                    continue

                state.user_data["email"] = email
                await send_text(ws, "Thank you! Now, let's understand your financial goals better.")
              
                
                # Move to financial concern step
                state.step = "get_financial_concern"
                # Send the financial concern buttons
                await send_buttons(
                    ws,
                    "What's your biggest financial concern right now?",
                    [
                        {"label": "Protecting my family's income", "value": "income_protection"},
                        {"label": "Covering medical expenses", "value": "medical_expenses"},
                        {"label": "Saving for children's education", "value": "education"},
                        {"label": "Building long-term wealth", "value": "wealth_building"},
                        {"label": "Planning for retirement", "value": "retirement"}
                    ]
                )
                state.step = "get_financial_concern_response"
                continue
            elif state.step == "get_financial_concern_response":
                state.user_data["primary_concern"] = message_content.strip()
                await send_buttons(
                    ws,
                    "Which best describes your current life stage?",
                    [
                        {"label": "Just starting a family", "value": "starting_family"},
                        {"label": "Raising young children", "value": "raising_children"},
                        {"label": "Paying off a home", "value": "home_owner"},
                        {"label": "Nearing retirement", "value": "pre_retirement"},
                        {"label": "Single and independent", "value": "single"},
                        {"label": "Retired", "value": "retired"}
                    ]
                )
                state.step = "get_life_stage"
            elif state.step == "get_life_stage":
                state.user_data["life_stage"] = message_content.strip()
                # Move to the next step which will handle campaign recommendations
                state.step = "get_dependents"
                await send_buttons(
                    ws,
                    "How many people depend on your income?",
                    [
                        {"label": "Just myself", "value": "1"},
                        {"label": "1 other person", "value": "2"},
                        {"label": "2-3 people", "value": "3"},
                        {"label": "4+ people", "value": "4"}
                    ]
                )
                state.step = "get_dependents"
            elif state.step == "get_dependents":
                state.user_data["dependents"] = message_content.strip()
                await send_buttons(
                    ws,
                    "Do you have any existing life or medical insurance?",
                    [
                        {"label": "No coverage at all", "value": "none"},
                        {"label": "Basic employer coverage", "value": "basic"},
                        {"label": "Some personal coverage", "value": "some"},
                        {"label": "Comprehensive coverage", "value": "full"}
                    ]
                )
                state.step = "get_existing_coverage"
            elif state.step == "get_existing_coverage":
                state.user_data["existing_coverage"] = message_content.strip()
                await send_buttons(
                    ws,
                    "What's your budget for monthly premiums? (RM)",
                    [
                        {"label": "< RM200", "value": "<200"},
                        {"label": "RM201 - RM500", "value": "201-500"},
                        {"label": "RM501 - RM1000", "value": "501-1000"},
                        {"label": "> RM1000", "value": ">1000"}
                    ]
                )
                state.step = "get_premium_budget"
            elif state.step == "get_premium_budget":
                state.user_data["premium_budget"] = message_content.strip()
                await send_text(ws, "Thank you for sharing your details! Let me analyze the best options for you...")
                
                # Reset any previous campaign state
                state.active_campaign = None
                state.campaign_state = None
                
                
                # Show campaign options
                await show_campaign_options(ws, state)
                state.step = "campaign_selection"
                
            elif state.step == "campaign_selection":
                # Handle campaign selection response
                try:
                    # If no message content, just show the options again
                    if not message_content.strip():
                        await show_campaign_options(ws, state)
                        continue
                        
                    # If user selected a campaign number
                    if message_content.isdigit():
                        selected_idx = int(message_content) - 1  # Convert to 0-based index
                        
                        # Define the exact campaign IDs in the order they are displayed
                        campaign_ids = [
                            "masa_depan_anak_kita",  # Option 1
                            "perlindungan_combo",     # Option 2
                            "sgsa",                   # Option 3 (SGSA)
                            "tabung_perubatan",       # Option 4
                            "tabung_warisan"          # Option 5
                        ]
                        
                        if 0<= selected_idx < len(campaign_ids):
                            campaign_id = campaign_ids[selected_idx]
                            state.user_data['selected_plan'] =campaign_id
                            state.step = f"campaign_{campaign_id}"

 
                           
                    
                        
                        # Update the displayed campaigns in user data
                        state.user_data['displayed_campaigns'] = campaign_ids
                        
                        # Define campaign mappings with proper display names
                        campaign_mappings = {
                            "sgsa": "Satu Gaji Satu Harapan (Income Protection)",
                            "tabung_perubatan": "Tabung Perubatan (Medical)",
                            "masa_depan_anak_kita": "Masa Depan Anak Kita (Education)",
                            "tabung_warisan": "Tabung Warisan (Retirement)",
                            "perlindungan_combo": "Perlindungan Combo (Comprehensive)"
                        }
                        
                        # Check if selected index is valid
                        if 0 <= selected_idx < len(campaign_ids):
                            campaign_id = campaign_ids[selected_idx]
                            state.active_campaign = campaign_id
                            state.step = f"campaign_{campaign_id}"
                            
                            # Log the campaign selection
                            logger.info(f"Selected campaign: {campaign_id} (index: {selected_idx})")
                            logger.info(f"Available campaign IDs: {campaign_ids}")
                            
                            # Get the display name from the mapping
                            display_name = campaign_mappings.get(campaign_id, campaign_id.replace('_', ' ').title())
                            logger.info(f"Display name: {display_name}")
                            
                            # Get the campaign instance from the already imported handlers
                            campaign_instance = campaign_handlers.get(campaign_id)
                            if not campaign_instance:
                                logger.error(f"No handler found for campaign: {campaign_id}")
                                await send_text(ws, "Sorry, there was an error starting the selected campaign. Please try again later.")
                                await show_campaign_options(ws, state)
                                continue
                            
                            # Log campaign launch info
                            logger.info(f"Starting campaign: {campaign_id} ({display_name})")
                            logger.info(f"Campaign instance type: {type(campaign_instance).__name__}")
                            
                            # Reset any previous campaign state
                            if hasattr(campaign_instance, 'states') and conv_id in campaign_instance.states:
                                del campaign_instance.states[conv_id]
                                logger.info(f"Reset previous state for user {conv_id} in campaign {campaign_id}")
                            
                            # Create the state dictionary for the campaign
                            campaign_state = {
                                "user_id": conv_id,
                                "message": "start",  # Use 'start' to trigger welcome flow
                                "campaign_data": state.user_data,
                                "campaign_id": campaign_id,
                                "campaign_display_name": display_name,
                                "current_step": "welcome",  # Initialize with welcome step
                                "user_data": {},  # Initialize empty user data for the campaign
                                "welcome_shown": False,  # Track if welcome message has been shown
                                "skip_initial_welcome": False  # Don't skip initial welcome
                            }
                            
                            try:
                                # Log campaign instance details
                                logger.info(f"Campaign instance type: {type(campaign_instance).__name__}")
                                logger.info(f"Campaign instance methods: {[m for m in dir(campaign_instance) if not m.startswith('_')]}")
                                
                                # Set the active campaign and initialize state
                                state.active_campaign = campaign_id
                                state.campaign_state = type('CampaignState', (), campaign_state)()
                                campaign_handlers[campaign_id] = campaign_instance
                                
                                # Initialize campaign state in the campaign instance
                                if hasattr(campaign_instance, 'get_state'):
                                    campaign_instance.get_state(conv_id)  # This will initialize the state if it doesn't exist
                                
                                # Log the campaign start
                                logger.info(f"Starting {campaign_id} campaign for user {conv_id}")
                                
                                # Handle the campaign with process_message
                                if hasattr(campaign_instance, 'process_message'):
                                    try:
                                        # Always send 'start' to initialize the campaign
                                        logger.info(f"Sending 'start' to initialize campaign {campaign_id}")
                                        
                                        # Call process_message with 'start' to get the welcome message
                                        result = await campaign_instance.process_message(
                                            user_id=conv_id,
                                            message="start",
                                            ws=ws,
                                            user_data=state.user_data  # Pass user data inc
                                        )
                                        
                                        # If we got a response, send it to the user
                                        if result and isinstance(result, dict) and ('response' in result or 'message' in result):
                                            # Get the response content from either 'response' or 'message' field
                                            response_content = result.get('response', result.get('message', ''))
                                            
                                            # Check if this is a button message
                                            if result.get('type') == 'buttons':
                                                response_data = {
                                                    "type": "buttons",
                                                    "content": response_content,
                                                    "text": response_content,
                                                    "buttons": result.get('buttons', []),
                                                    "is_user": False,
                                                    "timestamp": datetime.now().isoformat()
                                                }
                                                await ws.send_json(response_data)
                                                logger.info(f"[DEBUG] Sent buttons response: {response_data}")
                                            else:
                                                # Regular text message
                                                await send_text(ws, response_content)
                                                logger.info(f"[DEBUG] Sent text response: {response_content}")
                                            
                                            # Update the campaign state if needed
                                            if 'next_step' in result:
                                                state.step = f"campaign_{campaign_id}"
                                            state.campaign_initialized = True
                                            
                                            # Don't process further, wait for user response
                                            continue
                                        else:
                                            logger.info(f"Processing message in campaign {campaign_id}: {message_content}")
                                            result = await campaign_instance.process_message(
                                                user_id=conv_id,
                                                message=message_content,
                                                ws=ws,
                                                user_data=state.user_data  # Pass user data including DOB
                                            )
                                        
                                        if result and isinstance(result, dict):
                                            next_step = result.get('next_step')
                                            
                                            # Get the content from either 'content' or 'response' field
                                            content = result.get('content', result.get('response', ''))
                                            
                                            # If the response already has a type of 'buttons', use it as-is
                                            if result.get('type') == 'buttons':
                                                response_data = {
                                                    "type": "buttons",
                                                    "content": content,
                                                    "text": content,
                                                    "buttons": result.get('buttons', []),
                                                    "is_user": False,
                                                    "timestamp": datetime.now().isoformat()
                                                }
                                            else:
                                                # For regular messages, prepare the response object
                                                response_data = {
                                                    "type": result.get('type', 'message'),
                                                    "text": content,  # Frontend expects 'text' for the message
                                                    "content": content,  # Keep for backward compatibility
                                                    "is_user": False,
                                                    "timestamp": datetime.now().isoformat()
                                                }
                                            
                                            # Ensure we're not sending both message and content if they're the same
                                            if 'message' in response_data and 'content' in response_data and response_data['message'] == response_data['content']:
                                                del response_data['message']
                                            
                                            # Send the complete response
                                            await ws.send_text(json.dumps(response_data))
                                            
                                            # Handle campaign selection response
                                            if result.get('type') == 'campaign_selection' or result.get('return_to_campaign_select'):
                                                logger.info("Handling campaign selection response")
                                                state.active_campaign = None
                                                state.campaign_state = None
                                                
                                                # Prepare the campaign selection response
                                                response_data = {
                                                    "type": "campaign_selection",
                                                    "text": "Returning to campaign selection...",
                                                    "content": "Returning to campaign selection...",
                                                    "is_user": False,
                                                    "timestamp": datetime.now().isoformat()
                                                }
                                                
                                                # Send the response and continue to next iteration
                                                await ws.send_text(json.dumps(response_data))
                                                continue  # Skip the rest of the loop
                                                
                                            # If this is an end_conversation, handle it immediately
                                            if next_step == 'end_conversation':
                                                state.active_campaign = None
                                                state.step = "show_campaigns"
                                                await show_campaign_options(ws, state, show_all=state.user_data.get('showing_all_campaigns', False))
                                                continue  # Skip the rest of the loop
                                            
                                            if next_step:
                                                logger.info(f"Transitioning to next step: {next_step}")
                                                
                                    except Exception as e:
                                        logger.error(f"Error in campaign {campaign_id} process_message: {str(e)}", exc_info=True)
                                        raise
                                # Handle campaigns with start method
                                elif hasattr(campaign_instance, 'start') and callable(campaign_instance.start):
                                    logger.info(f"Calling start() on campaign instance: {campaign_id}")
                                    try:
                                        await campaign_instance.start(ws, conv_id)
                                    except Exception as e:
                                        logger.error(f"Error in campaign {campaign_id} start: {str(e)}", exc_info=True)
                                        raise
                                else:
                                    raise AttributeError("Campaign instance has no start() or process_message() method")
                                
                                # State is already set at the beginning of the try block
                                
                                # Log the campaign start
                                logger.info(f"Started campaign: {campaign_id} for user {conv_id}")
                                
                            except Exception as e:
                                logger.error(f"Error starting campaign {campaign_id}: {str(e)}", exc_info=True)
                                await send_text(ws, "Sorry, there was an error starting the selected campaign. Please try again later.")
                                await show_campaign_options(ws, state, show_all=state.user_data.get('showing_all_campaigns', False))
                                continue
                    elif message_content.lower() == "all":
                        # Show all campaigns
                        state.user_data['showing_all_campaigns'] = True
                        await show_campaign_options(ws, state, show_all=True)
                    # Process the message through the campaign handler if one exists
                    if state.active_campaign and state.active_campaign in campaign_handlers:
                        try:
                            handler = campaign_handlers[state.active_campaign]
                            logger.info(f"Processing message in campaign handler for {state.active_campaign}")
                            
                            # Add a timeout to prevent hanging
                            try:
                                import asyncio
                                # Pass user_data to the campaign's process_message method
                                result = await asyncio.wait_for(
                                    handler.process_message(conv_id, message_content, ws, user_data=state.user_data),
                                    timeout=30.0  # 30 second timeout
                                )
                                logger.info(f"Successfully processed message for {state.active_campaign}")
                                
                                # Handle the response from the campaign
                                if result and isinstance(result, dict):
                                    # Handle conversation state transitions first
                                    next_step = result.get('next_step')
                                    
                                    # If this is an end_conversation, handle it immediately
                                    if next_step == 'end_conversation':
                                        state.active_campaign = None
                                        state.step = "show_campaigns"
                                        if 'response' in result:
                                            await send_text(ws, result['response'])
                                        await show_campaign_options(ws, state, show_all=state.user_data.get('showing_all_campaigns', False))
                                        continue  # Skip the rest of the loop
                                    
                                    # For normal responses, send the message and buttons if available
                                    if 'response' in result:
                                        await send_text(ws, result['response'])
                                    
                                    if 'buttons' in result and result['buttons']:
                                        await send_buttons(
                                            ws,
                                            result.get('message', 'Please select an option:'),
                                            [{"label": btn['label'], "value": btn['value']} for btn in result['buttons']]
                                        )
                                    
                                    if next_step:
                                        logger.info(f"Transitioning to next step: {next_step}")
                                
                            except asyncio.TimeoutError:
                                logger.error(f"Timeout processing message for {state.active_campaign}")
                                await send_text(ws, "⌛ The operation is taking longer than expected. Please try again.")
                                
                        except Exception as e:
                            error_msg = f"Error processing message in campaign handler: {str(e)}"
                            logger.error(error_msg, exc_info=True)
                            
                            # Try to get a more specific error message
                            error_detail = str(e).lower()
                            
                            # Don't reset the conversation for common user input issues
                            if any(term in error_detail for term in ['invalid', 'unexpected', 'not found', 'missing']):
                                await send_text(ws, f"❌ {str(e)} Please try again.")
                                logger.info("Non-critical error - keeping conversation state")
                            else:
                                # More serious error, reset the conversation
                                logger.error("Critical error - resetting conversation")
                                state.active_campaign = None
                                state.step = "show_campaigns"
                                await send_text(ws, "❌ We encountered an issue. Let's start over. Please select an option from the menu.")
                                await show_campaign_options(ws, state, show_all=state.user_data.get('showing_all_campaigns', False))
                            continue  # Skip the rest of the loop
                    else:
                        # If no active campaign, show campaign options
                        await show_campaign_options(ws, state, show_all=state.user_data.get('showing_all_campaigns', False))
                except Exception as e:
                    logger.error(f"Error handling campaign selection: {str(e)}", exc_info=True)
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "content": "Sorry, we encountered an error processing your selection. Please try again.",
                        "is_user": False
                    }, ensure_ascii=False))
            else:
                response = {"type": "message", "content": "Conversation completed."}
                conversation_active = False
            if response:
                await ws.send_text(json.dumps(response))
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {conv_id}")
            break
        except Exception as e:
            logger.error(f"Error in WebSocket connection {conv_id}: {str(e)}", exc_info=True)
            # Skip sending error message if it's a duplicate or connection is closed
            if "WebSocket is not connected" not in str(e):
                try:
                    await ws.send_text(json.dumps({
                        "type": "error", 
                        "content": "❌ An error occurred. Let's start over.",
                        "reset": True  # Signal frontend to reset the chat
                    }))
                except Exception as send_error:
                    if "WebSocket is not connected" not in str(send_error):
                        logger.error(f"Failed to send error message: {str(send_error)}")
            break  # Exit the loop on error
    
    # Clean up conversation state after disconnect or error
    if conv_id in active_conversations:
        del active_conversations[conv_id]

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get port from environment variable or default to 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        # Required for WebSocket support
        ws_ping_interval=20,
        ws_ping_timeout=20,
        timeout_keep_alive=60
    )
    print(f"Starting server on port {port}...")
    print(f"WebSocket URL: ws://localhost:{port}/ws")
