from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union
import logging
import json
import asyncio
import time
from datetime import datetime
from Google_Sheet import append_row_to_sheet

logger = logging.getLogger(__name__)

def format_currency(amount):
    return f"RM {amount:,.2f}"

def calculate_premium_estimation(annual_income, years_of_coverage, age):
    """
    Calculate insurance premium estimation based on annual income, years of coverage, and age.
    
    Args:
        annual_income (float): Annual income in RM
        years_of_coverage (int): Number of years for coverage
        age (int): Current age of the applicant
        
    Returns:
        dict: Dictionary containing premium details
    """
    # Calculate recommended coverage (10x annual income)
    recommended_coverage = annual_income * 10
    
    # Determine premium rate based on age
    if age <= 30:
        premium_rate_per_thousand = 1.20
    elif age <= 40:
        premium_rate_per_thousand = 1.70
    elif age <= 50:
        premium_rate_per_thousand = 2.80
    else:
        premium_rate_per_thousand = 4.50
    
    # Calculate annual premium
    units_of_coverage = recommended_coverage / 1000
    estimated_annual_premium = units_of_coverage * premium_rate_per_thousand
    
    # Calculate monthly premium
    estimated_monthly_premium = estimated_annual_premium / 12
    
    # Ensure premium is not too low (minimum premium)
    estimated_annual_premium = max(estimated_annual_premium, 100)  # Minimum RM100 annual premium
    estimated_monthly_premium = estimated_annual_premium / 12
    
    return {
        'recommended_coverage': recommended_coverage,
        'annual_premium': round(estimated_annual_premium, 2),
        'monthly_premium': round(estimated_monthly_premium, 2),
        'premium_rate_per_thousand': premium_rate_per_thousand,
        'age': age,
        'years_of_coverage': years_of_coverage,
        'annual_income': annual_income
    }

@dataclass
class CampaignState:
    """State management for Satu Gaji Satu Harapan campaign."""
    current_step: str = "welcome"
    user_data: Dict[str, Any] = field(default_factory=dict)
    welcome_shown: bool = False
    
    def reset(self):
        """Reset the state to initial values."""
        self.__init__()

class SatuGajiSatuHarapan:
    """Main handler for Satu Gaji Satu Harapan campaign."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            self.states: Dict[str, CampaignState] = {}
            self.last_active: Dict[str, float] = {}
            self.name = "Satu Gaji Satu Harapan"
            self.description = "Income protection and financial security plan"
            self.initialized = True
    
    def get_state(self, user_id: str) -> CampaignState:
        """Get or create state for a user."""
        if user_id not in self.states:
            self.states[user_id] = CampaignState()
            self.last_active[user_id] = datetime.now().timestamp()
        return self.states[user_id]
    
    async def type_effect(self, text: str, ws=None, delay: float = 0.03) -> None:
        """Display text with typing effect or send through WebSocket."""
        try:
            if ws:
                print(f"[DEBUG] Sending message to WebSocket: {text[:100]}...")  # Log first 100 chars
                message = json.dumps({"type": "message", "content": text, "is_user": False})
                print(f"[DEBUG] JSON message: {message}")
                await ws.send_text(message)
                print("[DEBUG] Message sent successfully")
                await asyncio.sleep(delay * len(text) * 0.1)
            else:
                print(f"[DEBUG] Console output: {text[:100]}...")  # Log first 100 chars
                for char in text:
                    try:
                        print(char, end='', flush=True)
                        time.sleep(delay)
                    except (UnicodeEncodeError, Exception) as e:
                        print(f"[WARNING] Error printing character: {e}")
                        print(' ', end='', flush=True)
                print()
        except Exception as e:
            print(f"[ERROR] Error in type_effect: {str(e)}")
            if ws:
                print(f"[DEBUG] WebSocket state: open={not ws.client_state == 3}")
    
    async def get_user_input(self, prompt: str, valid_responses: Optional[list] = None, ws=None):
        """Get user input with validation."""
        if ws:
            # WebSocket mode
            await self.type_effect(prompt, ws)
            while True:
                try:
                    data = await ws.receive_text()
                    try:
                        message = json.loads(data)
                        if isinstance(message, dict) and "content" in message:
                            user_input = str(message["content"]).strip()
                        else:
                            user_input = str(message).strip()
                        
                        if not valid_responses or user_input.lower() in [str(r).lower() for r in valid_responses]:
                            return user_input
                        
                        if valid_responses is not None:
                            await self.type_effect(
                                f"Please respond with one of: {', '.join(str(r) for r in valid_responses)}",
                                ws
                            )
                    except json.JSONDecodeError:
                        user_input = data.strip()
                        if not valid_responses or user_input.lower() in [str(r).lower() for r in valid_responses]:
                            return user_input
                except Exception as e:
                    logger.error(f"Error getting user input: {e}")
                    await self.type_effect("Sorry, I had trouble understanding that. Could you please try again?", ws)
        else:
            # Console mode
            while True:
                try:
                    user_input = input(prompt).strip()
                    if not valid_responses or user_input.lower() in [str(r).lower() for r in valid_responses]:
                        return user_input
                    print(f"Please respond with one of: {', '.join(str(r) for r in valid_responses)}")
                except (EOFError, KeyboardInterrupt):
                    print("\nExiting...")
                    exit(1)
    
    def get_benefits(self):
        """Return the list of benefits for this campaign."""
        return [
            {
                "title": "INCOME REPLACEMENT",
                "description": "Financial security for your family with a lump sum payment.",
                "points": [
                    "Maintains family's living standards",
                    "Covers daily expenses and bills",
                    "Financial cushion during tough times"
                ]
            },
            {
                "title": "HOME & EDUCATION",
                "description": "Protects your family's home and children's future.",
                "points": [
                    "Helps with mortgage payments",
                    "Secures education funds",
                    "Avoids financial hardship"
                ]
            },
            {
                "title": "PEACE OF MIND",
                "description": "Security for your family's future.",
                "points": [
                    "Family protection",
                    "Financial safety net",
                    "Stability when it matters most"
                ]
            }
        ]

    async def show_benefits(self) -> Dict[str, Any]:
        """Display the benefits to the user.
        
        Returns:
            Dict containing the benefits message and buttons with the following keys:
            - response: The message to display
            - buttons: List of button dictionaries with 'label' and 'value' keys
            - next_step: The next step in the conversation
        """
        try:
            benefits_content = """💰 *Satu Gaji Satu Harapan - Income Protection Plan*

Here's what makes our income protection plan special:

• *Income Replacement*: Get up to 80% of your monthly income if you're unable to work due to illness or injury
• *Flexible Coverage*: Choose coverage periods from 1 to 30 years
• *Affordable Premiums*: Premiums start from as low as RM50 per month
• *No Medical Check-up Required*: Quick and easy application process
• *Tax Relief*: Enjoy tax relief on your premiums paid

Would you like to get a personalized quote?"""
            
            buttons = [
                {"label": "✅ Yes, get a quote", "value": "get_quote"},
                {"label": "❌ No, thanks", "value": "no"}
            ]
            
            logger.info("[SGSA] Generated benefits content and buttons")
            
            # Create response with all required fields
            response = {
                "type": "buttons",
                "response": benefits_content,
                "content": benefits_content, 
                "buttons": buttons,
                "next_step": "premium_decision"
            }
            
            logger.info(f"[SGSA] Sending benefits response: {json.dumps({k: v for k, v in response.items() if k != 'campaign_data'}, default=str)}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error in show_benefits: {e}", exc_info=True)
            return {
                "response": "I'm having trouble showing the benefits. Please try again later.",
                "error": str(e),
                "next_step": "welcome_response"
            }

    async def start_premium_estimation(self, ws=None):
        """Start the premium estimation process.
        
        Args:
            ws: WebSocket connection (kept for backward compatibility)
            
        Returns:
            Dict containing the response to start premium estimation
        """
        try:
            return {
                "response": "Let's get started with your premium estimation. I'll need a few details from you.\n\nWhat is your annual income? (e.g., RM50,000 or 50000)",
                "next_step": "get_annual_income"
            }
        except Exception as e:
            logger.error(f"Error in start_premium_estimation: {str(e)}", exc_info=True)
            return {
                "response": "I encountered an error starting the premium estimation. Please try again.",
                "next_step": "error"
            }
    
    async def start(self, ws, user_id: str) -> Dict[str, Any]:
        """Start the campaign flow for a user.
        
        Args:
            ws: WebSocket connection (kept for backward compatibility)
            user_id: Unique identifier for the user
            
        Returns:
            Dict containing the welcome message and buttons
        """
        try:
            logger.info(f"[SGSA] Starting campaign for user {user_id}")
            
            # Initialize user state
            state = self.get_state(user_id)
            state.current_step = "welcome"
            state.welcome_shown = True
            
            # Get welcome message
            welcome_msg = self.get_welcome_message().strip()
            
            # Return welcome message with buttons
            return self._create_button_response(
                content=welcome_msg,
                buttons=[
                    {"label": "✅ Yes, tell me more", "value": "yes"},
                    {"label": "❌ No, thanks", "value": "no"}
                ],
                next_step="welcome_response"
            )
            
        except Exception as e:
            logger.error(f"Error in start method: {e}", exc_info=True)
            return {
                "response": "An error occurred while starting the campaign. Please try again later.",
                "error": str(e),
                "completed": False
            }

    async def _handle_welcome(self, user_id: str, message: Union[str, dict], state: CampaignState) -> Dict[str, Any]:
        """Handle the welcome step of the conversation.
        
        Args:
            user_id: The user's unique identifier
            message: The message from the user (can be string or dict for button clicks)
            state: The current conversation state
            
        Returns:
            Dict containing the response to send to the user
        """
        logger.info(f"[SGSA] In _handle_welcome with message: {message} (type: {type(message)})")
        
        # If we already showed the welcome message, move to response handling
        if hasattr(state, 'welcome_shown') and state.welcome_shown:
            logger.info("[SGSA] Welcome already shown, moving to welcome response")
            return await self._handle_welcome_response(user_id, message, state)
            
        # Show welcome message with buttons
        welcome_msg = self.get_welcome_message().strip()
        state.welcome_shown = True
        
        # Create response with buttons
        response = self._create_button_response(
            content=welcome_msg,
            buttons=[
                {"label": "✅ Yes, tell me more", "value": "yes"},
                {"label": "❌ No, thanks", "value": "no"}
            ],
            next_step="welcome_response"
        )
        
        logger.info(f"[SGSA] Sending welcome message with buttons: {json.dumps(response, default=str)}")
        return response
    
    async def _handle_welcome_response(self, user_id: str, message: Union[str, dict], state: CampaignState) -> Dict[str, Any]:
        """Handle the user's response to the welcome message.
        
        Args:
            user_id: The user's unique identifier
            message: The message from the user (can be string or dict for button clicks)
            state: The current conversation state
            
        Returns:
            Dict containing the response to send to the user
        """
        logger.info(f"[SGSA] Handling welcome response: {message} (type: {type(message)})")
        
        try:
            # Handle button click or text input
            button_value = None
            text_input = ""
            
            # Handle different message formats
            if isinstance(message, dict):
                # Handle button click
                if 'value' in message:
                    button_value = message['value']
                    logger.info(f"[SGSA] Extracted button value: {button_value}")
                    # Normalize the button value
                    button_value = str(button_value).lower().strip()
                elif 'text' in message:
                    # Handle text input from WebSocket
                    text_input = str(message['text']).lower().strip()
            elif isinstance(message, str):
                # Handle direct text input
                text_input = message.lower().strip()
            
            logger.info(f"[SGSA] Processed input - button: {button_value}, text: {text_input}")
            
            # Check for positive response (button or text)
            positive_responses = ["yes", "y", "ya", "yeah", "yes, tell me more"]
            negative_responses = ["no", "n", "no thanks"]
            
            if (button_value and button_value.lower() in positive_responses) or \
               (text_input and text_input.lower() in positive_responses):
                # Show benefits
                logger.info("[SGSA] User wants to know more, showing benefits...")
                benefits_response = await self.show_benefits()
                if benefits_response:
                    logger.info("[SGSA] Successfully got benefits response")
                    state.current_step = "awaiting_premium_decision"
                    # Ensure the response includes the type field
                    if 'type' not in benefits_response:
                        benefits_response['type'] = 'message'
                    return benefits_response
                else:
                    logger.error("[SGSA] Failed to get benefits response")
                    return {
                        "type": "message",
                        "response": "I'm having trouble showing the benefits. Please try again later.",
                        "next_step": "welcome"
                    }
            elif (button_value and button_value.lower() in negative_responses) or \
                 (text_input and text_input.lower() in negative_responses):
                logger.info("[SGSA] User declined, ending conversation")
                state.current_step = "complete"
                return {
                    "type": "buttons",
                    "response": "Thank you for your interest in Satu Gaji Satu Harapan. If you have any questions, feel free to ask!",
                    "buttons": [
                        {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                    ],
                    "completed": True
                }
            else:
                # Unrecognized response, show welcome again with buttons
                logger.warning(f"[SGSA] Unrecognized response: {message}")
                welcome_msg = self.get_welcome_message().strip()
                return self._create_button_response(
                    content=welcome_msg,
                    buttons=[
                        {"label": "✅ Yes, tell me more", "value": "yes"},
                        {"label": "❌ No, thanks", "value": "no"}
                    ],
                    next_step="welcome_response"
                )
                
        except Exception as e:
            logger.error(f"Error in _handle_welcome_response: {e}", exc_info=True)
            return {
                "response": "An error occurred while processing your response. Please try again.",
                "next_step": "welcome"
            }
            
    async def _handle_premium_decision(self, user_id: str, message: Union[str, dict], state: CampaignState) -> Dict[str, Any]:
        """Handle the user's decision about getting a premium estimate.
        
        Args:
            user_id: The user's unique identifier
            message: The message from the user (can be string or dict for button clicks)
            state: The current conversation state
            
        Returns:
            Dict containing the response to send to the user
        """
        logger.info(f"[SGSA] Handling premium decision: {message} (type: {type(message)})")
        
        try:
            # Handle button click or text input
            button_value = None
            text_input = ""
            
            # Handle different message formats
            if isinstance(message, dict):
                # Handle button click
                if 'value' in message:
                    button_value = message['value']
                    logger.info(f"[SGSA] Extracted button value: {button_value}")
                    # Normalize the button value
                    button_value = str(button_value).lower().strip()
                elif 'text' in message:
                    # Handle text input from WebSocket
                    text_input = str(message['text']).lower().strip()
            elif isinstance(message, str):
                # Handle direct text input
                text_input = message.lower().strip()
            
            logger.info(f"[SGSA] Processed input - button: {button_value}, text: {text_input}")
            
            # Check for positive response (button or text)
            positive_responses = ["yes", "y", "ya", "yeah", "show coverage", "show me", "get_quote"]
            negative_responses = ["no", "n", "no thanks"]
            
            if (button_value and button_value.lower() in positive_responses) or \
               (text_input and text_input.lower() in positive_responses):
                # Start the premium estimation process
                logger.info("[SGSA] User wants to get a quote")
                state.current_step = "get_annual_income"
                return {
                    "type": "message",
                    "response": "To provide you with an accurate estimate, I'll need a few details.\n\nWhat is your annual income? (e.g., RM50,000 or 50000)",
                    "next_step": "get_annual_income"
                }
            elif (button_value and button_value.lower() in negative_responses) or \
                 (text_input and text_input.lower() in negative_responses):
                logger.info("[SGSA] User declined premium estimation")
                state.current_step = "complete"
                return {
                    "type": "buttons",
                    "response": "No problem! If you have any other questions or need assistance in the future, feel free to ask!",
                    "buttons": [
                        {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                    ],
                    "completed": True
                }
            else:
                # Unrecognized response, show benefits again
                logger.warning(f"[SGSA] Unrecognized response: {message}")
                benefits_response = await self.show_benefits()
                if benefits_response:
                    state.current_step = "awaiting_premium_decision"
                    return {
                        "type": "buttons",
                        "response": "I'm not sure I understand. Please select one of the options below.\n\n" + benefits_response.get('response', ''),
                        "buttons": benefits_response.get('buttons', []),
                        "next_step": benefits_response.get('next_step', 'awaiting_premium_decision')
                    }
                else:
                    return {
                        "type": "message",
                        "response": "I'm having trouble with that request. Let's start over.",
                        "next_step": "welcome"
                    }
                    
        except Exception as e:
            logger.error(f"Error in _handle_premium_decision: {e}", exc_info=True)
            return {
                "type": "message",
                "response": "An error occurred while processing your request. Please try again.",
                "next_step": "awaiting_premium_decision"
            }
    
    def _create_button_response(self, content: str, buttons: List[Dict[str, str]], next_step: str, **kwargs) -> Dict[str, Any]:
        """Helper method to create a standardized button response.
        
        Args:
            content: The message content to display
            buttons: List of button dictionaries with 'label' and 'value' keys
            next_step: The next step in the conversation
            **kwargs: Additional fields to include in the response
            
        Returns:
            A dictionary with the response format expected by the WebSocket handler
        """
        response = {
            "type": "buttons",
            "response": content,
            "content": content,  # For backward compatibility
            "buttons": buttons,
            "next_step": next_step,
            "timestamp": datetime.now().isoformat()
        }
        response.update(kwargs)  # Add any additional fields
        
        # Log the response for debugging
        logger.info(f"[SGSA] Created button response: {json.dumps({k: v for k, v in response.items() if k != 'campaign_data'}, default=str)}")
        
        return response

    async def process_message(self, user_id: str, message: Union[str, dict], ws=None, **kwargs) -> Dict[str, Any]:
        # Handle return to main menu from button
        is_button_click = isinstance(message, dict) and ('value' in message or 'type' in message)
        if is_button_click:
            message_text = str(message.get('value', '')).lower().strip()
        else:
            message_text = str(message).lower().strip() if message else ""

        if message_text == "main_menu":
            logger.info("[SGSA] User selected Return to Main Menu. Resetting to get_name.")
            state = CampaignState()
            self.states[user_id] = state
            return {
                "type": "reset_to_main",
                "response": "Returning to main menu...",
                "content": "Returning to main menu...",
                "reset_to_main": True
            }
        """Process incoming message and return response.
        
        Args:
            user_id: Unique identifier for the user
            message: The message from the user (can be string or dict for button clicks)
            ws: WebSocket connection (kept for backward compatibility)
            **kwargs: Additional arguments including user_data
            
        Returns:
            Dict containing the response to send to the user with the following keys:
            - response: The message to display
            - buttons: List of button dictionaries (optional)
            - next_step: The next step in the conversation
        """
        logger.info(f"[SGSA] ==== START process_message ====")
        logger.info(f"[SGSA] User ID: {user_id}")
        logger.info(f"[SGSA] Raw message: {message} (type: {type(message)})")
        
        try:
            # Get or create user state
            state = self.get_state(user_id)
            logger.info(f"[SGSA] Current state: {state.__dict__ if hasattr(state, '__dict__') else state}")
            
            # Initialize state if needed
            if not hasattr(state, 'current_step') or not state.current_step:
                state.current_step = "welcome"
                logger.info("[SGSA] Initialized new state with welcome step")
            
            # Update last active timestamp
            self.last_active[user_id] = datetime.now().timestamp()
            
            # Update state with any provided user data
            user_data = kwargs.get('user_data', {})
            if user_data:
                if not hasattr(state, 'user_data'):
                    state.user_data = {}
                state.user_data.update(user_data)
                logger.info(f"[SGSA] Updated user data: {state.user_data}")
            
            # Handle button click responses - extract value if it's a button click
            is_button_click = isinstance(message, dict) and ('value' in message or 'type' in message)
            if is_button_click:
                logger.info(f"[SGSA] Processing button click: {message}")
                message_text = str(message.get('value', '')).lower().strip()
                logger.info(f"[SGSA] Extracted button value: {message_text}")
            else:
                # Regular text message
                message_text = str(message).lower().strip() if message else ""
                logger.info(f"[SGSA] Processing text message: {message_text}")
            
            logger.info(f"[SGSA] Current step before handling: {state.current_step}")
            
            # Handle special commands
            if message_text == "restart":
                # Reset state
                state = CampaignState()
                self.states[user_id] = state
                logger.info("[SGSA] Restarting conversation")
                return await self.start(ws, user_id)
                
            if message_text == "start":
                logger.info("[SGSA] Restarting conversation via start command")
                return await self.start(ws, user_id)
            
            # Handle different steps in the conversation
            current_step = state.current_step
            logger.info(f"[SGSA] Processing message in step: {current_step}")
            
            # Handle premium estimation flow
            if current_step == "premium_estimation":
                # This is now a fallback state in case we need it
                state.current_step = "awaiting_premium_decision"
                return await self.process_message(user_id, message, ws)
                
            # Route to appropriate handler based on current step
            handler_name = f"_handle_{current_step}"
            if hasattr(self, handler_name):
                handler = getattr(self, handler_name)
                logger.info(f"[SGSA] Routing to handler: {handler_name}")
                try:
                    # For button clicks, pass the full message object
                    # For text, just pass the text
                    handler_arg = message if is_button_click else message_text
                    logger.info(f"[SGSA] Calling handler with arg: {handler_arg}")
                    
                    response = await handler(user_id, handler_arg, state)
                    
                    # Ensure response is a dictionary
                    if not isinstance(response, dict):
                        logger.error(f"[SGSA] Handler {handler_name} did not return a dict: {response}")
                        return {
                            "response": "I encountered an error. Let's try that again.",
                            "next_step": current_step
                        }
                    
                    # Log the response before returning
                    loggable_response = {k: v for k, v in response.items() if k != 'campaign_data'}
                    logger.info(f"[SGSA] Handler {handler_name} returned: {loggable_response}")
                    
                    # Update the current step if next_step is provided in the response
                    if 'next_step' in response:
                        old_step = current_step
                        state.current_step = response['next_step']
                        logger.info(f"[SGSA] Updated step from '{old_step}' to '{state.current_step}'")
                    
                    return response
                    
                except Exception as e:
                    logger.error(f"[SGSA] Error in handler {handler_name}: {e}", exc_info=True)
                    return {
                        "response": "An error occurred while processing your request. Please try again.",
                        "next_step": current_step
                    }
            
            # If no handler found, try to handle the step directly
            if hasattr(self, '_handle_step_directly'):
                return await self._handle_step_directly(state, message_text, ws, user_id)
                
            # Handle specific steps directly
            if current_step == "get_annual_income":
                return await self._handle_get_annual_income(user_id, message, state, ws)
            elif current_step == "get_age":
                return await self._handle_get_age(user_id, message, state, ws)
            elif current_step == "get_years_coverage":
                return await self._handle_years_coverage(user_id, message, state, ws)
            elif current_step == "calculate_premium":
                return await self._handle_calculate_premium(user_id, message, state, ws)
            elif current_step == "handle_agent_decision":
                return await self._handle_agent_decision(user_id, message, state, ws)
            elif current_step == "complete":
                completion_msg = """
🙏 Thank you for considering 'Satu Gaji, Satu Harapan'.
Protecting your family's future is the greatest gift you can give."""
                
                await self.type_effect(completion_msg, ws)
                
                if ws:
                    return {
                        "response": "Would you like to return to campaign selection? (yes/no)",
                        "campaign_data": state["data"],
                        "completed": True
                    }
                else:
                    return {
                        "response": "💬 Would you like to return to campaign selection? (yes/no)",
                        "campaign_data": state["data"],
                        "completed": True
                    }
                
            # Default response if no handler found
            logger.warning(f"[SGSA] No handler found for step: {current_step}")
            return {
                "response": "I'm not sure how to process that. Let's start over.",
                "next_step": "welcome"
            }
                
        except Exception as e:
            logger.error(f"Error in process_message: {e}", exc_info=True)
            # Return error response
            return {
                "response": "An error occurred while processing your message. Please try again.",
                "error": str(e),
                "completed": False,
                "next_step": "welcome"  # Reset to welcome step on error
            }
    
    async def _handle_get_annual_income(self, user_id: str, message: Union[str, dict], state: Dict[str, Any], ws=None) -> Dict[str, Any]:
        """Handle the user's annual income input.
        
        Args:
            user_id: The user's unique identifier
            message: The message from the user (can be string or dict for button clicks)
            state: The current conversation state
            ws: WebSocket connection (kept for backward compatibility)
            
        Returns:
            Dict containing the response to send to the user
        """
        logger.info(f"[SGSA] Handling annual income input: {message} (type: {type(message)})")
        
        try:
            # Debug: Log the raw message and its type
            logger.debug(f"[SGSA] Raw message: {message}, Type: {type(message)}")
            
            # Extract the message text
            if isinstance(message, dict):
                logger.debug("[SGSA] Processing dictionary input")
                if 'text' in message:
                    message_text = str(message['text']).strip()
                elif 'value' in message:
                    message_text = str(message['value']).strip()
                else:
                    message_text = str(message).strip()
            else:
                message_text = str(message).strip()
            
            logger.debug(f"[SGSA] Extracted message text: '{message_text}'")
            
            # Check for empty input
            if not message_text:
                logger.warning("[SGSA] Empty input received")
                return {
                    "response": "Please enter your annual income (e.g., 50000 or RM50,000):",
                    "next_step": "get_annual_income"
                }
            
            # Clean the input - remove all non-digit characters except decimal point
            cleaned_input = ''.join(c for c in message_text if c.isdigit() or c == '.')
            logger.debug(f"[SGSA] Cleaned input: '{cleaned_input}'")
            
            # If no digits found, check for word numbers
            if not cleaned_input:
                logger.debug("[SGSA] No digits found, checking for word numbers")
                word_to_num = {
                    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
                    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
                    'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70,
                    'eighty': 80, 'ninety': 90, 'hundred': 100, 'thousand': 1000
                }
                
                # Check for word numbers
                message_lower = message_text.lower()
                logger.debug(f"[SGSA] Checking for word numbers in: {message_lower}")
                
                for word, num in word_to_num.items():
                    if word in message_lower:
                        annual_income = num * 1000  # Assume thousands if word input
                        logger.debug(f"[SGSA] Found word number: {word} = {num}, annual_income = {annual_income}")
                        break
                else:
                    logger.warning(f"[SGSA] No valid number found in input: {message_text}")
                    raise ValueError("No valid number found in input")
            else:
                # Try to convert to float
                try:
                    annual_income = float(cleaned_input)
                    logger.debug(f"[SGSA] Successfully converted to float: {annual_income}")
                except ValueError as e:
                    logger.error(f"[SGSA] Failed to convert '{cleaned_input}' to float: {str(e)}")
                    raise ValueError("Invalid number format") from e
            
            # Validate the income amount
            if annual_income <= 0:
                logger.warning(f"[SGSA] Invalid annual income input: {message_text}")
                return {
                    "response": "Please enter a positive amount for annual income:",
                    "next_step": "get_annual_income"
                }
            
            # Store the annual income in user data
            if not hasattr(state, 'user_data'):
                state.user_data = {}
            state.user_data['annual_income'] = annual_income
            
            # Check if we have DOB in user_data and can calculate age
            if 'dob' in state.user_data and state.user_data['dob']:
                try:
                    from datetime import datetime
                    # Handle both DD/MM/YYYY and YYYY-MM-DD formats
                    dob = state.user_data['dob']
                    if '/' in dob:
                        day, month, year = map(int, dob.split('/'))
                        dob_date = datetime(year=year, month=month, day=day)
                    else:  # Assuming YYYY-MM-DD format
                        dob_date = datetime.strptime(dob, '%Y-%m-%d')
                    
                    today = datetime.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    
                    # Store the calculated age and move to next step
                    state.user_data['age'] = age
                    state.current_step = "get_years_coverage"
                    
                    response_msg = f"Got it! Your annual income is {format_currency(annual_income)}.\n\n" \
                                 f"Great! I see you're {age} years old. " \
                                 f"How many years of coverage would you like? (e.g., 10, 20, or 30 years)"
                    
                    return {
                        "response": response_msg,
                        "next_step": "get_years_coverage"
                    }
                except Exception as e:
                    logger.error(f"[SGSA] Error calculating age from DOB: {str(e)}", exc_info=True)
                    # Continue to manual age input if DOB calculation fails
            
            # If no DOB or error in calculation, ask for age
            state.current_step = "get_age"
            return {
                "response": f"Got it! Your annual income is RM{format_currency(annual_income)}.\n\nNow, please enter your age:",
                "next_step": "get_age"
            }
                
        except Exception as e:
            logger.error(f"Error in _handle_get_annual_income: {e}", exc_info=True)
            return {
                "response": "An error occurred while processing your income information. Please try again with a valid amount (e.g., 50000 or RM50,000):",
                "next_step": "get_annual_income"
            }

    async def _handle_get_age(self, user_id: str, message: Union[str, dict], state: Dict[str, Any], ws=None) -> Dict[str, Any]:
        """Handle the get_age step of the conversation."""
        try:
            # Check if we have DOB in user_data and calculate age from it
            if hasattr(state, 'user_data') and 'dob' in state.user_data and state.user_data['dob']:
                try:
                    from datetime import datetime
                    # Handle both DD/MM/YYYY and YYYY-MM-DD formats
                    dob = state.user_data['dob']
                    if '/' in dob:
                        day, month, year = map(int, dob.split('/'))
                        dob_date = datetime(year=year, month=month, day=day)
                    else:  # Assuming YYYY-MM-DD format
                        dob_date = datetime.strptime(dob, '%Y-%m-%d')
                    
                    today = datetime.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    
                    # Store the calculated age
                    state.user_data['age'] = age
                    logger.info(f"[SGSA] Calculated age {age} from DOB: {dob}")
                    
                    # Prepare response message
                    response_msg = f"Great! I see you're {age} years old. " \
                                 f"How many years of coverage would you like? (e.g., 10, 20, or 30 years)\n" \
                                 "This is the duration you want your insurance protection to last."
                    
                    # Move to next step
                    state.current_step = "get_years_coverage"
                    
                    # Send through WebSocket if available
                    if ws:
                        await ws.send_text(json.dumps({
                            "type": "message",
                            "content": response_msg,
                            "is_user": False
                        }))
                    
                    return {
                        "response": response_msg,
                        "campaign_data": state.user_data,
                        "waiting_for_response": True,
                        "next_step": "get_years_coverage"
                    }
                except Exception as e:
                    logger.error(f"[SGSA] Error calculating age from DOB: {str(e)}", exc_info=True)
                    # Continue with manual age input if DOB calculation fails
            
            # If no DOB or error in calculation, proceed with manual age input
            try:
                # Ensure message is a string
                message_str = str(message).strip()
                logger.info(f"[SGSA] Processing manual age input: {message_str}")
                
                # Extract number from input
                word_to_num = {
                    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
                    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
                    'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70
                }
                
                age = None
                message_lower = message_str.lower()
                
                # Check for word numbers first
                for word, num in word_to_num.items():
                    if word in message_lower:
                        age = num
                        break
                
                # If no word number found, try to extract digits
                if age is None:
                    import re
                    digits = re.search(r'\d+', message_str)
                    if digits:
                        age = int(digits.group())
                    else:
                        raise ValueError("No valid number found in age input")
                
                # Validate range
                if age < 18 or age > 70:
                    error_msg = "Please enter an age between 18 and 70."
                    if ws:
                        await ws.send_text(json.dumps({
                            "type": "message",
                            "content": error_msg,
                            "is_user": False
                        }))
                    return {
                        "response": error_msg,
                        "campaign_data": state.user_data,
                        "waiting_for_response": True
                    }
                
                # Store age and move to next step
                if not hasattr(state, 'user_data'):
                    state.user_data = {}
                state.user_data["age"] = age
                state.current_step = "get_years_coverage"
                
                # Prepare response message
                response_msg = f"Great! You're {age} years old. " \
                             f"How many years of coverage would you like? (e.g., 10, 20, or 30 years)\n" \
                             "This is the duration you want your insurance protection to last."
                
                # Send through WebSocket if available
                if ws:
                    await ws.send_text(json.dumps({
                        "type": "message",
                        "content": response_msg,
                        "is_user": False
                    }))
                
                return {
                    "response": response_msg,
                    "campaign_data": state.user_data,
                    "waiting_for_response": True,
                    "next_step": "get_years_coverage"
                }
                
            except Exception as e:
                error_msg = "Please enter a valid age (e.g., '20', '20 years', or 'twenty')."
                logger.error(f"[SGSA] Error processing manual age input: {str(e)}", exc_info=True)
                
                if ws:
                    await ws.send_text(json.dumps({
                        "type": "message",
                        "content": error_msg,
                        "is_user": False
                    }))
                
                return {
                    "response": error_msg,
                    "campaign_data": state.user_data,
                    "waiting_for_response": True
                }
                
        except Exception as e:
            error_msg = "An unexpected error occurred while processing your age. Please try again."
            logger.error(f"[SGSA] Unexpected error in _handle_get_age: {str(e)}", exc_info=True)
            
            if ws:
                await ws.send_text(json.dumps({
                    "type": "message",
                    "content": error_msg,
                    "is_user": False
                }))
            
            return {
                "response": error_msg,
                "campaign_data": state.user_data if hasattr(state, 'user_data') else {},
                "waiting_for_response": True
            }

    async def _handle_years_coverage(self, user_id: str, message: Union[str, dict], state: Dict[str, Any], ws=None) -> Dict[str, Any]:
        """Handle the years of coverage input."""
        try:
            # Extract years from message
            years = int(str(message).strip())
            
            # Validate range (1-50 years)
            if years < 1 or years > 50:
                error_msg = "Please enter a number between 1 and 50 years."
                if ws:
                    await ws.send_text(json.dumps({
                        "type": "message",
                        "content": error_msg,
                        "is_user": False
                    }))
                return {
                    "response": error_msg,
                    "campaign_data": state.user_data,
                    "waiting_for_response": True
                }
            
            # Store years and move to next step
            if not hasattr(state, 'user_data'):
                state.user_data = {}
            state.user_data["years_of_coverage"] = years
            state.current_step = "calculate_premium"
            
            # Process to next step
            return await self._handle_calculate_premium(user_id, message, state, ws)
            
        except ValueError:
            error_msg = "Please enter a valid number of years (e.g., 10, 20, or 30)."
            if ws:
                await ws.send_text(json.dumps({
                    "type": "message",
                    "content": error_msg,
                    "is_user": False
                }))
            return {
                "response": error_msg,
                "campaign_data": state.user_data,
                "waiting_for_response": True
            }

    async def _handle_calculate_premium(self, user_id: str, message: Union[str, dict], state: Dict[str, Any], ws=None) -> Dict[str, Any]:
        """Calculate and display the premium based on user inputs."""
        try:
            logger.info("[DEBUG] Starting premium calculation...")
            # Get the collected data
            if not hasattr(state, 'user_data'):
                state.user_data = {}
            annual_income = state.user_data.get("annual_income")
            age = state.user_data.get("age")
            years_of_coverage = state.user_data.get("years_of_coverage")
            
            logger.info(f"[DEBUG] Input values - Annual Income: {annual_income}, Age: {age}, Years of Coverage: {years_of_coverage}")
            
            if not all([annual_income, age, years_of_coverage]):
                missing = []
                if not annual_income: missing.append("annual_income")
                if not age: missing.append("age")
                if not years_of_coverage: missing.append("years_of_coverage")
                error_msg = f"Missing required information for premium calculation: {', '.join(missing)}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Ensure types are correct
            try:
                annual_income = float(annual_income)
                age = int(age)
                years_of_coverage = int(years_of_coverage)
                logger.info(f"[DEBUG] Converted values - Annual Income: {annual_income} ({type(annual_income)}), "
                          f"Age: {age} ({type(age)}), "
                          f"Years of Coverage: {years_of_coverage} ({type(years_of_coverage)})")
            except (ValueError, TypeError) as e:
                error_msg = f"Error converting input values: {str(e)}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Calculate premium
            logger.info("[DEBUG] Calling calculate_premium_estimation...")
            premium_info = calculate_premium_estimation(annual_income, years_of_coverage, age)
            logger.info(f"[DEBUG] Premium calculation result: {premium_info}")
            
            #Google Sheets Insertion
            try:
                name = state.user_data.get("name", "N/A")
                dob = state.user_data.get("dob","")
                email = state.user_data.get("email","")
                primary_concern = state.user_data.get("primary_concern", "")
                life_stage = state.user_data.get("life_stage", "")
                dependents = state.user_data.get("dependents", "")
                existing_coverage = state.user_data.get("existing_coverage", "")
                premium_budget = state.user_data.get("premium_budget", "")
                selected_plan = state.user_data.get("selected_plan", "sgsa")

                #Campaign specific data
                annual_income_str = str(annual_income)
                coverage_str = str(years_of_coverage)

                #row data
                row_data = [
                name, dob, email, primary_concern, life_stage, dependents,
                existing_coverage, premium_budget, selected_plan,
                annual_income_str, coverage_str  # New: annual_income, coverage, monthly_premiu
             ]
                append_row_to_sheet(row_data)
                logger.info (f"[SGSA] Data inserted to Google Sheet:{annual_income_str}, Coverage={coverage_str} for user {user_id}")

            except Exception as sheet_error:
                logger.error(f"[SGSA]Error inserting data to Google Sheets: {str(sheet_error)}")

            # Format the response
            response_msg = (
                f"Based on your details:\n"
                f"• Annual Income: RM{annual_income:,.2f}\n"
                f"• Age: {age}\n"
                f"• Coverage Period: {years_of_coverage} years\n\n"
                f"Your estimated premium:\n"
                f"• Recommended Coverage: RM{premium_info['recommended_coverage']:,.2f}\n"
                f"• Estimated Annual Premium: RM{premium_info['annual_premium']:,.2f}\n"
                f"• Estimated Monthly Premium: RM{premium_info['monthly_premium']:,.2f}\n\n"
                "Would you like to speak with an agent to proceed with this plan?"
            )
            
            # Update state
            state.current_step = "handle_agent_decision"
            
            # Create button response
            return self._create_button_response(
                content=response_msg,
                buttons=[
                    {"label": "✅ Yes, contact me", "value": "yes_contact"},
                    {"label": "❌ No thanks", "value": "no_contact"}
                ],
                next_step="handle_agent_decision",
                campaign_data=state.user_data
            )
            
        except Exception as e:
            logger.error(f"Error calculating premium: {str(e)}", exc_info=True)
            error_msg = "An error occurred while calculating your premium. Please try again."
            if ws:
                await ws.send_text(json.dumps({
                    "type": "message",
                    "content": error_msg,
                    "is_user": False
                }))
            return {
                "response": error_msg,
                "campaign_data": state.user_data,
                "waiting_for_response": True,
                "next_step": "welcome"
            }

    async def _handle_agent_decision(self, user_id: str, message: Union[str, dict], state: Dict[str, Any], ws=None) -> Dict[str, Any]:
        """Handle the user's decision about speaking with an agent."""
        try:
            logger.info(f"[DEBUG] In handle_agent_decision, message: {message}")
            
            # Extract message value if it's a button click
            if isinstance(message, dict) and 'value' in message:
                message = message['value']
                
            message_lower = str(message).lower().strip()
            
            if message_lower in ['yes', 'y', 'ya', 'yeah', 'yes_contact', 'contact_agent']:
                # User wants to be contacted by an agent
                logger.info("User requested agent contact. Showing Main Menu button...")
                return self._create_button_response(
                    content="Thank you! An agent will contact you soon. If you wish to return to the main menu, click below.",
                    buttons=[
                        {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                    ],
                    next_step="handle_agent_decision",
                    campaign_data=state.user_data
                )
            elif message_lower in ['no', 'n', 'no_contact', 'no thanks']:
                logger.info("User declined agent contact. Showing Main Menu button...")
                return self._create_button_response(
                    content="No problem! If you wish to return to the main menu, click below.",
                    buttons=[
                        {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                    ],
                    next_step="handle_agent_decision",
                    campaign_data=state.user_data
                )
                
            elif message_lower == "main_menu" or message_lower == "restart":
                logger.info("Main menu or restart selected. Signaling main.py to reset and start from get_name...")
                return {
                    "type": "reset_to_main",
                    "response": "Returning to main menu...",
                    "content": "Returning to main menu...",
                    "reset_to_main": True
                }
                
            else:
                # If we get here, it's not a recognized command
                return self._create_button_response(
                    content="Would you like an agent to contact you to further discuss the plan?",
                    buttons=[
                        {"label": "✅ Yes, contact me", "value": "contact_agent"},
                        {"label": "❌ No thanks", "value": "no_contact"},
                        {"label": "🏠 Main Menu", "value": "main_menu"}
                    ],
                    next_step="offer_agent_contact",
                    campaign_data=state.user_data
                )
                
        except Exception as e:
            logger.error(f"Error handling agent decision: {str(e)}", exc_info=True)
            error_msg = "An error occurred while processing your request. Please try again."
            if ws:
                await ws.send_text(json.dumps({
                    "type": "message",
                    "content": error_msg,
                    "is_user": False
                }))
            return {
                "response": error_msg,
                "campaign_data": state["data"],
                "waiting_for_response": True,
                "next_step": "handle_agent_decision"
            }

    def get_welcome_message(self) -> str:
        return """
🌟 Welcome to 'Satu Gaji Satu Harapan' Income Protection! 🌟

Your income is your most valuable asset. This plan ensures you and your family are protected if you're unable to work due to illness or injury.

With this plan, you can:
• Replace your income if you can't work
• Get financial support during recovery
• Protect your family's future

Would you like to know more about this plan?
"""

# Create a singleton instance
class SatuGajiSatuHarapanCampaign(SatuGajiSatuHarapan):
    """Wrapper class for the Satu Gaji Satu Harapan campaign."""
    
    async def main(self, ws, state):
        """Main entry point for the campaign.
        
        Args:
            ws: WebSocket connection
            state: Conversation state
        """
        try:
            # Initialize or get user state
            user_id = str(id(ws))  # Use WebSocket ID as user ID
            
            # Start the campaign flow
            await self.start(ws, user_id)
        except Exception as e:
            logger.error(f"Error in main: {e}", exc_info=True)
            await ws.send_json({
                "type": "message",
                "content": "An error occurred while starting the campaign. Please try again later.",
                "error": str(e)
            })

# Create singleton instance
sgsa_campaign = SatuGajiSatuHarapanCampaign()

# Alias for backward compatibility
satu_gaji_satu_harapan_instance = sgsa_campaign

# Main function for direct execution
async def main(ws, state):
    """Main entry point for the campaign.
    
    Args:
        ws: WebSocket connection
        state: Conversation state
    """
    await sgsa_campaign.main(ws, state)

# For testing the campaign directly
if __name__ == "__main__":
    class MockWebSocket:
        def __init__(self):
            self.messages = []
            
        async def send_text(self, message: str):
            self.messages.append(message)
            print(f"Bot: {message}")
    
    async def test_campaign():
        ws = MockWebSocket()
        user_id = "test_user"
        campaign = SatuGajiSatuHarapan()
        
        # Test welcome message
        await campaign.process_message(user_id, "start", ws)
        
        # Simulate user responses
        responses = [
            "1",  # Start premium estimation
            "50000",  # Annual income
            "20",  # Years of coverage
            "30",  # Age
            "yes"  # Confirm details
        ]
        
        for response in responses:
            print(f"\nUser: {response}")
            await campaign.process_message(user_id, response, ws)
    
    asyncio.run(test_campaign())
