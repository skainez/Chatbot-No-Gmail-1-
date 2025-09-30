from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union
import logging
import json
import asyncio
from datetime import datetime
from Google_Sheet import append_row_to_sheet

logger = logging.getLogger(__name__)


def format_currency(amount: float) -> str:
    return f"RM {amount:,.2f}"


def future_value_annuity(payment: float, rate: float, years: int) -> float:
    """Calculate future value of annual contributions."""
    return payment * (((1 + rate) ** years - 1) / rate)

@dataclass
class CampaignState:
    """State management for Masa Depan Anak Kita campaign."""
    current_step: str = "welcome"
    user_data: Dict[str, Any] = field(default_factory=dict)
    child_age: Optional[int] = None
    monthly_saving: Optional[float] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    
    def reset(self):
        """Reset the state to initial values."""
        self.__init__()

class MasaDepanAnakKita:
    """Main handler for Masa Depan Anak Kita campaign."""
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
            self.name = "Masa Depan Anak Kita"
            self.description = "Education savings plan for your child's future"
            self.initialized = True
    
    def _normalize_input(self, text: str) -> str:
        """Normalize user input for consistent processing."""
        if not text:
            return ""
        return text.strip().lower()
    
    def _is_affirmative(self, text: str) -> bool:
        """Check if the user's response is affirmative."""
        if not text:
            return False
        return any(affirmative in text.lower() for affirmative in [
            "yes", "y", "ya", "yeah", "yup", "yep", "sure", "ok", "okay", 
            "alright", "continue", "proceed", "affirmative", "certainly", 
            "definitely", "absolutely", "yes please", "of course"
        ])
    
    def _is_negative(self, text: str) -> bool:
        """Check if the user's response is negative."""
        if not text:
            return False
        return any(negative in text.lower() for negative in [
            "no", "n", "nope", "nah", "no thanks", "not now", "not yet",
            "later", "maybe later", "i'll pass", "skip", "stop", "cancel",
            "exit", "quit", "end"
        ])
    
    def _get_help_message(self, current_step: str) -> str:
        """Get context-sensitive help message based on current step."""
        help_messages = {
            "welcome": "I can help you plan for your child's education. Just let me know if you'd like to know more!",
            "ask_about_plan": "Would you like to learn more about our education savings plan? (Yes/No)",
            "ask_about_estimation": "Would you like to see how much you need to save for your child's education? (Yes/No)",
            "get_child_age": "Please enter your child's age (0-17 years):",
            "get_monthly_saving": "How much would you like to save monthly? You can choose an option or enter a custom amount.",
            "default": "I'm here to help you plan for your child's education. Let me know if you have any questions!"
        }
        return help_messages.get(current_step, help_messages["default"])
        
    def get_state(self, user_id: str) -> CampaignState:
        """Get or create state for a user."""
        if user_id not in self.states:
            self.states[user_id] = CampaignState()
        self.last_active[user_id] = datetime.now().timestamp()
        return self.states[user_id]
        
    async def cleanup_old_states(self, max_age_seconds: int = 3600):
        """Remove states older than max_age_seconds."""
        now = datetime.now().timestamp()
        to_remove = [user_id for user_id, last_active in self.last_active.items() 
                    if now - last_active > max_age_seconds]
        for user_id in to_remove:
            self.states.pop(user_id, None)
            self.last_active.pop(user_id, None)
    
    async def send_message(self, message: str, ws: Any = None) -> Dict[str, Any]:
        """Helper to format a text message response.
        
        Args:
            message: Message to send
            ws: Optional WebSocket connection (kept for backward compatibility)
            
        Returns:
            Dict containing the formatted response
        """
        if not message or not isinstance(message, str):
            logger.warning("Attempted to send empty or invalid message")
            return {
                "type": "message",
                "content": "",
                "is_user": False
            }
            
        logger.info(f"[MDK] Formatting message: {message[:100]}{'...' if len(message) > 100 else ''}")
        
        return {
            "type": "message",
            "content": message,
            "is_user": False
        }
    
    async def send_buttons(self, text: str, buttons: List[Dict[str, str]], ws: Any = None) -> Dict[str, Any]:
        """Format a message with buttons.
        
        Args:
            text: The message text
            buttons: List of button dicts with 'label' and 'value'
            ws: Optional WebSocket connection (kept for backward compatibility)
            
        Returns:
            Dict containing the formatted response with buttons
        """
        if not text or not isinstance(text, str):
            logger.warning("Attempted to send buttons with empty or invalid message")
            text = "Please select an option:"
            
        if not buttons or not isinstance(buttons, list):
            logger.warning("No valid buttons provided, formatting as text")
            return await self.send_message(text, ws)
            
        logger.info(f"[MDK] Formatting buttons: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        # Validate buttons
        valid_buttons = []
        for btn in buttons:
            if not isinstance(btn, dict) or 'label' not in btn or 'value' not in btn:
                logger.warning(f"Skipping invalid button: {btn}")
                continue
            valid_buttons.append({
                'label': str(btn['label']),
                'value': str(btn['value'])
            })
        
        if not valid_buttons:
            logger.warning("No valid buttons to format, falling back to text")
            return await self.send_message(text, ws)
        
        # Store buttons for reference
        self._last_buttons = valid_buttons
        
        return {
            "type": "buttons",
            "content": text,
            "buttons": valid_buttons,
            "is_user": False
        }

    async def _handle_help_request(self, message: str, state: CampaignState, ws: Any = None) -> Optional[Dict[str, Any]]:
        """Handle help requests from the user.
        
        Args:
            message: The user's message
            state: Current conversation state
            ws: Optional WebSocket connection (kept for backward compatibility)
            
        Returns:
            Dict containing the help response or None if not a help request
        """
        help_commands = ["help", "what can you do", "how does this work"]
        if message.lower() in help_commands:
            help_msg = self._get_help_message(state.current_step)
            return {
                "type": "message",
                "content": help_msg,
                "campaign_data": state.user_data,
                "next_step": state.current_step
            }
        return None
    
    async def process_message(self, user_id: str, message: Union[str, dict], ws: Any = None, user_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process incoming message and return response.
        
        Args:
            user_id: Unique identifier for the user session
            message: User's input message, can be string or dict
            ws: WebSocket connection for real-time updates
            user_data: Optional dictionary containing user data from main conversation
            
        Returns:
            Dict containing response and state information with next_step for flow control
        """
        try:
            # Get or create state for user
            state = self.get_state(user_id)
            
            # Update state with user data if provided
            if user_data:
                state.user_data.update(user_data)
                logger.info(f"[MDK] Updated user data from main conversation: {user_data}")
            
            # Extract message content if it's a dictionary
            message_content = message.get('text', '') if isinstance(message, dict) else str(message)
            logger.info(f"[MDK] Processing message in state {state.current_step}: {message_content}")
            
            # Update last active time
            self.last_active[user_id] = datetime.now().timestamp()
            
            # Handle special 'start' message to initialize the conversation
            if message.strip().lower() == "start":
                logger.info("[MDK] Received start message, initializing conversation")
                return await self.start(ws, user_id)
            
            # Check for help request
            help_response = await self._handle_help_request(message, state, ws)
            if help_response:
                return help_response
            
            # Sanitize and normalize input
            message = self._normalize_input(message_content)
            if not message:
                return {
                    "response": "I didn't catch that. Could you please try again?",
                    "campaign_data": state.user_data,
                    "next_step": state.current_step
                }
            
            logger.info(f"[MDK] Processing message for user {user_id}, step: {state.current_step}, message: '{message}'")
            
            # Handle conversation flow based on current step
            
            # Handle special commands
            if message == "main_menu" or message == "restart":
                logger.info("Main menu or restart selected. Signaling main.py to reset and start from get_name...")
                return {
                    "type": "reset_to_main",
                    "response": "Returning to main menu...",
                    "content": "Returning to main menu...",
                    "reset_to_main": True
                }
                
            # Handle welcome state response
            if state.current_step == "welcome":
                # Check if this is a button click (value will be 'yes' or 'no')
                    is_button_click = message.lower() in ['yes', 'no']

                    if is_button_click and message.lower() == 'yes' or self._is_affirmative(message):
                        # User wants to know more, show plan explanation with buttons
                        explanation_data = self.get_plan_explanation()
                        state.current_step = "ask_about_estimation"
                        response = {
                            "type": explanation_data["type"],
                            "content": explanation_data["content"],
                            "buttons": explanation_data["buttons"],
                            "campaign_data": state.user_data,
                            "next_step": "ask_about_estimation"
                        }
                        logger.info(f"[MDK] Showing plan explanation, next step: {state.current_step}")
                        return response
                    elif is_button_click and message.lower() == 'no' or self._is_negative(message):
                        # User doesn't want to continue, show only the return to main menu button
                        state.current_step = "end_options"
                        return {
                            "type": "buttons",
                            "content": "Thank you for your interest. You may return to the main menu below:",
                            "campaign_data": state.user_data,
                            "next_step": "end_options",
                            "buttons": [
                                {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                            ]
                        }
                    else:
                        # Invalid response, provide guidance with buttons
                        buttons = [
                            {"label": "✅ Yes, tell me more", "value": "yes"},
                            {"label": "❌ No, thanks", "value": "no"}
                        ]
                        return {
                            "type": "buttons",
                            "content": "I'm not sure I understand. Would you like to learn more about our education savings plan?",
                            "buttons": buttons,
                            "campaign_data": state.user_data,
                            "next_step": "welcome"
                        }
                
            # Handle response to initial welcome
            elif state.current_step == "ask_about_plan":
                logger.info(f"[MDK] Processing response to plan explanation: {message}")
                if self._is_affirmative(message) or message.lower() == 'yes':
                    # User wants to know more, show plan explanation with buttons
                    explanation_data = self.get_plan_explanation()
                    state.current_step = "ask_about_estimation"
                    
                    return {
                        "type": explanation_data["type"],
                        "content": explanation_data["content"],
                        "buttons": explanation_data["buttons"],
                        "campaign_data": state.user_data,
                        "next_step": "ask_about_estimation"
                    }
                else:
                    # User doesn't want to continue, offer return to main menu
                    state.current_step = "end_options"
                    return {
                        "type": "buttons",
                        "content": "No problem! Would you like to return to the main menu?",
                        "campaign_data": state.user_data,
                        "next_step": "end_options",
                        "buttons": [
                            {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                    
            # Handle response to estimation question
            elif state.current_step == "ask_about_estimation" or state.current_step == "waiting_for_estimation_response":
                # Log the user's response for debugging
                logger.info(f"[MDK] Processing estimation response: {message}")
                
                if self._is_affirmative(message) or "estimate" in message.lower() or message.lower() == "yes":
                    # User wants to see estimation, ask for child's age
                    state.current_step = "get_child_age"
                    return {
                        "type": "question",
                        "content": "Great! Let's calculate how much you need to save for your child's education.\n\nPlease enter your child's current age (0-17 years):",
                        "campaign_data": state.user_data,
                        "next_step": "get_child_age"
                    }
                else:
                    # User doesn't want to proceed with estimation, offer return to main menu
                    state.current_step = "end_options"
                    return {
                        "type": "buttons",
                        "content": "No problem! Would you like to return to the main menu?",
                        "campaign_data": state.user_data,
                        "next_step": "end_options",
                        "buttons": [
                            {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                
            # Handle welcome response
            if state.current_step == "welcome_response":
                if message.lower() in ["yes", "y"]:
                    # User is interested, ask for child's age
                    state.current_step = "get_child_age"
                    return {
                        "type": "message",
                        "content": "Great! To help us customize the plan for you, please enter your child's age (0-17 years):",
                        "campaign_data": state.user_data,
                        "next_step": "waiting_for_age"
                    }
                else:
                    # User declined, end the campaign
                    state.current_step = "end"
                    return {
                        "response": "No problem! If you change your mind or have any questions about education planning, feel free to ask. Have a great day!",
                        "campaign_data": state.user_data,
                        "next_step": "complete"
                    }
            
            # Handle child age input
            elif state.current_step in ["get_child_age", "waiting_for_age"]:
                try:
                    # Check for help request
                    if message.lower() in ["help", "?"]:
                        return {
                            "type": "message",
                            "content": "Please enter your child's current age (0-17 years). For example: '5' or 'my child is 5 years old'.",
                            "campaign_data": state.user_data,
                            "next_step": "waiting_for_age"
                        }
                    
                    # Check if user wants to start over
                    if message.lower() in ["start over", "restart"]:
                        return await self.handle_restart(message, state)
                    
                    # Extract numbers from the message
                    import re
                    numbers = re.findall(r'\d+', message)
                    if not numbers:
                        raise ValueError("Please enter a valid age (a number between 0 and 17). For example: '5' or 'my child is 5 years old'.")
                            
                    age = int(numbers[0])
                    if age < 0 or age > 17:
                        raise ValueError("Age must be between 0 and 17 years. Please enter a valid age.")
                    
                    # Store the age in state
                    state.child_age = age
                    logger.info(f"[MDK] Child's age set to: {age}")
                    saving_options = [
                        {"label": "RM 200/month", "value": "200"},
                        {"label": "RM 300/month", "value": "300"},
                        {"label": "RM 400/month", "value": "400"},
                        {"label": "RM 500/month", "value": "500"},
                        {"label": "Custom amount", "value": "custom"}
                    ]
                    
                    # Update state
                    state.current_step = "get_monthly_saving"
                    
                    # Prepare response with saving options
                    response = {
                        "type": "buttons",
                        "content": f"Thank you! Your child is {age} years old, which means you have about {18 - age} years until they start university.\n\nHow much would you like to save monthly for their education?",
                        "buttons": saving_options,
                        "campaign_data": state.user_data,
                        "next_step": "waiting_for_saving"
                    }
                    
                    logger.info(f"[MDK] Asking for monthly saving amount for child age {age}")
                    return response
                    
                except ValueError as e:
                    error_msg = f"❌ {str(e)}\n\n"
                    error_msg += "Please enter your child's age as a number between 0 and 17.\n\n"
                    error_msg += "Examples:\n"
                    error_msg += "- '5'\n"
                    error_msg += "- 'My child is 5 years old'\n"
                    error_msg += "- 'Age 5'\n\n"
                    error_msg += "If you need to start over, type 'start over'."
                    
                    logger.warning(f"[MDK] Invalid age input: {message}")
                    
                    return {
                        "type": "message",
                        "content": error_msg,
                        "campaign_data": state.user_data,
                        "next_step": "waiting_for_age"
                    }
            
            # Handle monthly saving amount selection
            elif state.current_step == "get_monthly_saving":
                try:
                    # Check for custom amount request
                    if message.lower() == "custom" or "custom" in message.lower():
                        state.current_step = "get_custom_saving"
                        return {
                            "type": "message",
                            "content": "Please enter your desired monthly saving amount (minimum RM 100):",
                            "campaign_data": state.user_data,
                            "next_step": "waiting_for_custom_saving"
                        }
                    
                    # Check if user is responding to the saving options
                    if message.lower() in ["yes", "y", "no", "n"]:
                        # User might be responding to a previous question, clarify
                        return {
                            "type": "message",
                            "content": "Please select one of the monthly saving options or choose 'Custom amount'.",
                            "campaign_data": state.user_data,
                            "next_step": "get_monthly_saving"
                        }
                    
                    # Process predefined amounts
                    amount_map = {
                        "200": 200, "1": 200, "rm200": 200, "rm 200": 200,
                        "300": 300, "2": 300, "rm300": 300, "rm 300": 300,
                        "400": 400, "3": 400, "rm400": 400, "rm 400": 400,
                        "500": 500, "4": 500, "rm500": 500, "rm 500": 500
                    }
                    
                    # Try to get amount from message (case insensitive)
                    message_lower = message.lower()
                    amount = None
                    
                    # Check for exact matches first
                    for key, value in amount_map.items():
                        if key == message_lower or f"rm{key}" in message_lower or f"rm {key}" in message_lower:
                            amount = value
                            break
                    
                    # If no exact match, try to extract number from message
                    if amount is None:
                        import re
                        numbers = re.findall(r'\d+', message)
                        if numbers:
                            amount = int(numbers[0])
                            # Validate the extracted number is one of the allowed amounts
                            if amount not in [200, 300, 400, 500]:
                                amount = None
                    
                    # If we have a valid amount, process it
                    if amount is not None and amount >= 100:
                        # Store the amount
                        state.monthly_saving = amount
                        
                        # Move to next step
                        state.current_step = "calculate_results"
                        
                        # Calculate and show results
                        return await self.calculate_results("", state)
                    
                    # If we get here, the input wasn't recognized as a valid amount
                    raise ValueError("Please select one of the options or choose 'Custom amount'.")
                    
                except ValueError as e:
                    response = {
                        "type": "message",
                        "content": f"❌ {str(e)}. Please select one of the options or choose 'Custom amount'.",
                        "campaign_data": state.user_data,
                        "next_step": "get_monthly_saving"
                    }
                    logger.warning(f"[MDK] Invalid saving amount input: {message}")
                    return response
                except Exception as e:
                    logger.error(f"[MDK] Error processing saving amount: {str(e)}", exc_info=True)
                    response = {
                        "type": "message",
                        "content": "I'm sorry, I encountered an error processing the amount. Please try again.",
                        "campaign_data": state.user_data,
                        "next_step": "get_monthly_saving"
                    }
                    return response
                    
            # Handle custom saving amount input
            elif state.current_step == "get_custom_saving":
                try:
                    # Check if user wants to go back to the options
                    if message.lower() in ["back", "options", "show options"]:
                        state.current_step = "get_monthly_saving"
                        # Return to the monthly saving options
                        saving_options = [
                            {"label": "RM 200/month", "value": "200"},
                            {"label": "RM 300/month", "value": "300"},
                            {"label": "RM 400/month", "value": "400"},
                            {"label": "RM 500/month", "value": "500"},
                            {"label": "Custom amount", "value": "custom"}
                        ]
                        return {
                            "type": "buttons",
                            "content": "Please select a monthly saving amount:",
                            "buttons": saving_options,
                            "campaign_data": state.user_data,
                            "next_step": "get_monthly_saving"
                        }

                    # Extract numbers from the message
                    import re
                    numbers = re.findall(r'\d+', message)
                    if not numbers:
                        raise ValueError("Please enter a valid amount (e.g., 250)")

                    amount = int(numbers[0])
                    if amount < 100:
                        raise ValueError(f"The minimum monthly saving is RM 100. You entered RM {amount}.")
                    if amount > 10000:
                        raise ValueError("That amount seems too high. Please enter an amount up to RM 10,000.")

                    # Store the amount
                    state.monthly_saving = amount

                    # Calculate projection
                    years = 18 - (state.child_age if state.child_age is not None else 0)
                    monthly_saving = amount
                    fv_low = future_value_annuity(monthly_saving, 0.06, years)
                    fv_base = future_value_annuity(monthly_saving, 0.08, years)
                    fv_high = future_value_annuity(monthly_saving, 0.10, years)

                    # Update Google Sheet
                    try:
                        name = state.user_data.get("name", "N/A")
                        dob = state.user_data.get("dob", "")
                        email = state.user_data.get("email", "")
                        primary_concern = state.user_data.get("primary_concern", "")
                        life_stage = state.user_data.get("life_stage", "")
                        dependents = state.user_data.get("dependents", "")
                        existing_coverage = state.user_data.get("existing_coverage", "")
                        premium_budget = state.user_data.get("premium_budget", "")
                        selected_plan = "masa_depan_anak_kita"
                        child_age_str = str(state.child_age)
                        monthly_saving_str = str(monthly_saving)

                        row_data = [
                            name, dob, email, primary_concern, life_stage, dependents,
                            existing_coverage, premium_budget, selected_plan,
                            None, None, None,
                            child_age_str, monthly_saving_str
                        ]
                        append_row_to_sheet(row_data)
                        logger.info(f"[MDK] Data inserted to Google Sheet: Child Age={child_age_str}, Monthly Saving={monthly_saving_str}")
                    except Exception as sheet_error:
                        logger.error(f"[MDK] Error inserting data to Google Sheet: {str(sheet_error)}")

                    # Format the response
                    result_message = (
                        "YOUR EDUCATION FUND PROJECTION\n"
                        f"{'='*10}\n"
                        f"- Child's current age: {state.child_age} years\n"
                        f"- Years until university: {years} years\n"
                        f"- Monthly saving: {format_currency(monthly_saving)}\n\n"
                        "Projected Fund:\n"
                        f"- At 6% return: {format_currency(fv_low)}\n"
                        f"- At 8% return: {format_currency(fv_base)}\n"
                        f"- At 10% return: {format_currency(fv_high)}\n\n"
                        "WHAT THIS MEANS:\n"
                        f"By saving {format_currency(monthly_saving)} monthly, you could accumulate between "
                        f"{format_currency(fv_low)} and {format_currency(fv_high)} by the time your child "
                        "reaches university age (18).\n\n"
                        "REMINDER: This is just an illustration, not an official quotation."
                    )

                    # Update state to complete
                    state.current_step = "complete"

                    # Combine results with contact prompt
                    combined_message = f"{result_message}\n\nWould you like an agent to contact you to further discuss the plan?"

                    return {
                        "type": "buttons",
                        "content": combined_message,
                        "campaign_data": state.user_data,
                        "next_step": "complete",
                        "buttons": [
                            {"label": "✅ Yes, contact me", "value": "contact_agent"},
                            {"label": "❌ No thanks", "value": "no_contact"}
                        ]
                    }

                except ValueError as e:
                    logger.warning(f"[MDK] Invalid custom saving amount: {message}")
                    return {
                        "type": "message",
                        "content": f"❌ {str(e)}\n\nPlease enter a valid amount between RM 100 and RM 10,000, or type 'back' to return to the options.",
                        "campaign_data": state.user_data,
                        "next_step": "get_custom_saving"
                    }
                except Exception as e:
                    logger.error(f"[MDK] Error processing custom saving amount: {str(e)}", exc_info=True)
                    return {
                        "type": "message",
                        "content": "I'm sorry, I encountered an error processing your input. Please try again or type 'back' to return to the options.",
                        "campaign_data": state.user_data,
                        "next_step": "get_custom_saving"
                    }
            
            # Handle completion and restart
            elif state.current_step == "complete":
                if message.lower() == "contact_agent":
                    # If user selects to be contacted by agent
                    return {
                        "type": "buttons",
                        "content": "Our agent will get to you soon. You should receive an email with information regarding our plans.\n\nHow else can we assist you today?",
                        "campaign_data": state.user_data,
                        "next_step": "contact_confirmation",
                        "buttons": [
                            {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                elif message.lower() == "request_contact":





                    
                    # Initial agent contact request
                    return {
                        "type": "buttons",
                        "content": "Would you like an agent to contact you to further discuss the plan?",
                        "campaign_data": state.user_data,
                        "next_step": "complete",
                        "buttons": [
                            {"label": "✅ Yes, contact me", "value": "contact_agent"},
                            {"label": "❌ No thanks", "value": "no_contact"}
                        ]
                    }
                elif message.lower() == "no_contact" or message.lower() == "no":
                    # User doesn't want to be contacted, offer return to main menu
                    return {
                        "type": "buttons",
                        "content": "Thank you for using Masa Depan Anak Kita. Would you like to return to the main menu?",
                        "campaign_data": state.user_data,
                        "next_step": "end_options",
                        "buttons": [
                            {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                elif self._is_affirmative(message) or message.lower() == "restart":
                    # Reset the state and start over
                    self.states[user_id] = CampaignState()
                    state = self.get_state(user_id)
                    welcome_msg = self.get_welcome_message()
                    
                    return {
                        "type": "message",
                        "content": welcome_msg,
                        "campaign_data": state.user_data,
                        "next_step": "welcome",
                        "buttons": [
                            {"label": "✅ Yes, tell me more", "value": "yes"},
                            {"label": "❌ No, thanks", "value": "no"}
                        ]
                    }
                else:
                    # Initial completion - ask if they want to be contacted
                    return {
                        "type": "buttons",
                        "content": "Would you like an agent to contact you to further discuss the plan?",
                        "campaign_data": state.user_data,
                        "next_step": "complete",
                        "buttons": [
                            {"label": "✅ Yes, contact me", "value": "contact_agent"},
                            {"label": "❌ No thanks", "value": "no_contact"}
                        ]
                    }
            
            # Handle return to main menu from end_options
            if state.current_step == "end_options" and message.lower() == "main_menu":
                self.states[user_id] = CampaignState()
                state = self.get_state(user_id)
                welcome_msg = self.get_welcome_message()
                return {
                    "type": "message",
                    "content": "Let's start over! What is your name?",
                    "campaign_data": state.user_data,
                    "next_step": "get_name"
                }
            # Handle unknown state or errors
            logger.warning(f"[MDK] Unknown state or error in state: {state.current_step}")
            state.current_step = "welcome"
            return {
                "type": "message",
                "content": "I'm sorry, I got a bit lost. Let's start over.",
                "campaign_data": state.user_data,
                "next_step": "welcome"
            }
            
        except Exception as e:
            # Catch-all for any unhandled exceptions
            logger.error(f"[MDK] Unhandled exception in process_message: {str(e)}", exc_info=True)
            state.current_step = "welcome"
            error_msg = "I'm sorry, I encountered an error processing your request. "
            error_msg += "Our team has been notified. Let's start over."
            
            return {
                "type": "message",
                "content": error_msg,
                "campaign_data": state.user_data if 'state' in locals() else {},
                "next_step": "welcome"
            }
            
    def get_welcome_message(self) -> str:
        return """
🌟 Welcome to 'Masa Depan Anak Kita' Education Fund Estimator! 🌟

This tool helps you estimate how much you need to save to secure your child's future education. We'll guide you through a simple process to create a personalized education savings plan.

Would you like to know more about this plan? (Yes/No)
"""
    
    def get_plan_explanation(self) -> Dict[str, Any]:
        """Get the plan explanation with interactive buttons.
        
        Returns:
            Dict containing the explanation message and response buttons
        """
        explanation = """
What is This Plan About?
----------------------
The Masa Depan Anak Kita plan is a comprehensive education savings solution that combines long-term savings with protection benefits. It's designed to help parents like you ensure that your child's education is financially secure, no matter what the future holds.

Key Benefits:
- Guaranteed education payouts at key education milestones
- Life insurance coverage for the parent
- Waiver of premium benefit in case of total permanent disability
- Flexible premium payment terms
- Potential annual bonuses to boost your savings

Would you like to see a rough estimation of how much you can save for your child's future education?
"""
        buttons = [
            {"label": "✅ Yes, show me", "value": "yes"},
            {"label": "❌ No, thanks", "value": "no"}
        ]
        
        return {
            "type": "buttons",
            "content": explanation,
            "buttons": buttons
        }
        
    async def start(self, ws, user_id: str, user_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start the campaign for a user.
        
        Args:
            ws: WebSocket connection (kept for backward compatibility)
            user_id: Unique identifier for the user
            user_data: Optional dictionary containing user data from main conversation
            
        Returns:
            Dict containing the welcome message and next step
        """
        try:
            # Initialize or get user state
            state = self.get_state(user_id)
            
            # Reset any existing state
            state.reset()
            state.current_step = "welcome"  # Set initial step to welcome
            
            # Update state with user data if provided
            if user_data:
                state.user_data.update(user_data)
                logger.info(f"[MDK] Updated user data in start: {user_data}")
            
            # Get welcome message
            welcome_msg = self.get_welcome_message().strip()
            buttons = [
                {"label": "✅ Yes, tell me more", "value": "yes"},
                {"label": "❌ No, thanks", "value": "no"}
            ]
            
            # Log the start of the campaign
            logger.info(f"[MDK] Starting campaign for user {user_id}")
            
            # Return the welcome message with buttons
            return {
                "type": "buttons",
                "content": welcome_msg,  # Frontend expects 'content' field
                "message": welcome_msg,  # Some frontend code might look for 'message'
                "text": welcome_msg,     # Some frontend code might look for 'text'
                "buttons": buttons,
                "campaign_data": state.user_data,
                "next_step": "welcome"  # Keep the same step to handle the response
            }
            
        except Exception as e:
            logger.error(f"Error in start method: {str(e)}", exc_info=True)
            return {
                "type": "message",
                "content": "An error occurred while starting the campaign. Please try again.",
                "campaign_data": {},
                "next_step": "welcome"
            }
    async def process_child_age(self, message: str, state: CampaignState) -> Optional[str]:
        """Process and validate the child's age input.
        
        Args:
            message: The user's input message containing the child's age
            state: The current conversation state
            
        Returns:
            The validated age as a string, or None if invalid
        """
        try:
            age = int(message.strip())
            if 0 <= age <= 17:
                state.user_data["child_age"] = age
                # Calculate years until college (assuming college starts at age 18)
                state.user_data["years_until_college"] = 18 - age
                return str(age)
            return None
        except (ValueError, TypeError):
            return None
            
    async def process_monthly_saving(self, message: str, state: CampaignState, ws: Any = None) -> Optional[float]:
        """Process and validate the monthly saving amount.
        
        Args:
            message: The user's input message containing the monthly saving amount or option
            state: The current conversation state
            ws: WebSocket connection for sending messages
            
        Returns:
            The validated monthly saving amount as a float, or None if invalid
        """
        try:
            # Handle option selection
            if message.strip() in ["1", "2", "3", "4"]:
                amounts = {"1": 200, "2": 300, "3": 400, "4": 500}
                amount = amounts[message.strip()]
            elif message.strip() == "5":
                # Request custom amount
                if ws:
                    await self.send_text("Please enter your desired monthly saving amount (minimum RM 100):", ws)
                    state.current_step = "get_custom_saving"
                return None
            else:
                # Handle direct amount input
                try:
                    # Remove any non-numeric characters except decimal point
                    amount_str = ''.join(c for c in message if c.isdigit() or c == '.')
                    if not amount_str:
                        return None
                        
                    amount = float(amount_str)
                    if amount < 100:  # Minimum saving amount
                        if ws:
                            await self.send_text("⚠️ Minimum monthly saving is RM 100. Please enter a higher amount.", ws)
                        return None
                        
                    state.user_data["monthly_saving"] = amount
                    return amount
                    
                except (ValueError, TypeError):
                    if ws:
                        await self.send_text("⚠️ Please enter a valid amount.", ws)
                    return None
            
            # If we got here, it's a valid option (1-4)
            state.user_data["monthly_saving"] = amount
            return amount
            
        except Exception as e:
            logger.error(f"Error processing monthly saving: {str(e)}")
            if ws:
                await self.send_text("⚠️ An error occurred. Please try again.", ws)
            return None
            
    async def calculate_results(self, message: str, state: CampaignState) -> Dict[str, Any]:
        """Calculate and return education fund projection results.
        
        Args:
            message: User's message (unused, kept for backward compatibility)
            state: Current conversation state
            
        Returns:
            Dict containing the formatted response with results
        """
        try:
            # Calculate years until university (18 - child's age)
            years = 18 - state.child_age
            monthly_saving = state.monthly_saving
            annual_contribution = monthly_saving * 12
            
            # Calculate projections
            fv_low = future_value_annuity(annual_contribution, 0.06, years)
            fv_base = future_value_annuity(annual_contribution, 0.08, years)
            fv_high = future_value_annuity(annual_contribution, 0.10, years)

            try:
                name = state.user_data.get("name", "N/A")
                dob = state.user_data.get("dob", "")
                email = state.user_data.get("email", "")
                primary_concern = state.user_data.get("primary_concern", "")
                life_stage = state.user_data.get("life_stage", "")
                dependents = state.user_data.get("dependents", "")
                existing_coverage = state.user_data.get("existing_coverage", "")
                premium_budget = state.user_data.get("premium_budget", "")
                selected_plan = "masa_depan_anak_kita"
                child_age_str = str(state.child_age)
                monthly_saving_str = str(state.monthly_saving)

                row_data = [
                    name, dob, email, primary_concern, life_stage, dependents,
                    existing_coverage, premium_budget, selected_plan,
                    None, None, None,  # SKIP 4 LAJUR: Kosongkan 4 kolom (e.g., for annual_income, coverage, etc.)
                    child_age_str, monthly_saving_str  # Data spesifik: Umur anak sekarang & jumlah tabungan bulanan
                ]

                append_row_to_sheet(row_data)
                logger.info(f"[MDK] Data inserted to Google Sheet: Child Age={child_age_str}, Monthly Saving={monthly_saving_str}")

            except Exception as sheet_error:
                logger.error(f"[MDK] Error inserting data to Google Sheet: {str(sheet_error)}")


            
            # Format the response
            result_message = (
                "YOUR EDUCATION FUND PROJECTION\n"
                f"{'='*10}\n"
                f"- Child's current age: {state.child_age} years\n"
                f"- Years until university: {years} years\n"
                f"- Monthly saving: {format_currency(monthly_saving)}\n\n"
                "Projected Fund:\n"
                f"- At 6% return: {format_currency(fv_low)}\n"
                f"- At 8% return: {format_currency(fv_base)}\n"
                f"- At 10% return: {format_currency(fv_high)}\n\n"
                "WHAT THIS MEANS:\n"
                f"By saving {format_currency(monthly_saving)} monthly, you could accumulate between "
                f"{format_currency(fv_low)} and {format_currency(fv_high)} by the time your child "
                "reaches university age (18).\n\n"
                "REMINDER: This is just an illustration, not an official quotation."
                
            )





            # Update state to complete
            state.current_step = "complete"
            
            # Combine results with contact prompt
            combined_message = f"{result_message}\n\nWould you like an agent to contact you to further discuss the plan?"
            
            return {
                "type": "buttons",
                "content": combined_message,
                "campaign_data": state.user_data,
                "next_step": "complete",
                "buttons": [
                    {"label": "✅ Yes, contact me", "value": "contact_agent"},
                    {"label": "❌ No thanks", "value": "no_contact"}
                ]
            }
            
        except Exception as e:
            logger.error(f"Error calculating results: {str(e)}", exc_info=True)
            return {
                "type": "message",
                "content": "I encountered an error calculating your results. Please try again.",
                "campaign_data": state.user_data if 'state' in locals() else {},
                "next_step": "error"
            }
    
    async def handle_restart(self, message: str, state: CampaignState) -> Dict[str, Any]:
        """Handle restarting the conversation.
        
        Args:
            message: The user's message
            state: Current conversation state
            
        Returns:
            Dict containing the restart response with welcome message and buttons
        """
        try:
            # Reset the state
            state.reset()
            state.current_step = "ask_about_plan"
            
            # Get welcome message
            welcome_msg = "🔁 Great! Let's start over.\n\n" + self.get_welcome_message()
            buttons = [
                {"label": "✅ Yes, tell me more", "value": "yes"},
                {"label": "❌ No, thanks", "value": "no"}
            ]
            
            return {
                "type": "buttons",
                "content": welcome_msg,
                "buttons": buttons,
                "campaign_data": state.user_data,
                "next_step": "waiting_for_plan_response"
            }
        except Exception as e:
            logger.error(f"Error in handle_restart: {str(e)}", exc_info=True)
            return {
                "type": "message",
                "content": "An error occurred while restarting the conversation. Please try again.",
                "campaign_data": state.user_data if 'state' in locals() else {},
                "next_step": "error"
            }


# Create a singleton instance
masa_depan_anak_kita_campaign = MasaDepanAnakKita()

async def main(ws, state):
    """Main entry point for the campaign.

    Args:
        ws: WebSocket connection
        state: Conversation state
    """
    # Initialize or get user state
    user_id = id(ws)  # Use WebSocket ID as user ID
    
    # Start the campaign flow
    await masa_depan_anak_kita_campaign.start(ws, user_id)