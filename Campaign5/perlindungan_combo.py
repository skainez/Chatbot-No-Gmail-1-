from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple, Union
import logging
import json
import asyncio
from datetime import datetime, date  # Import datetime and date classes
import sys
from pathlib import Path
import re
from Google_Sheet import append_row_to_sheet

# Add parent directory to path to access main.py
sys.path.append(str(Path(__file__).parent.parent))

# Import active_conversations from main
try:
    from main import active_conversations
except ImportError:
    active_conversations = {}
    logger = logging.getLogger(__name__)
    logger.warning("Could not import active_conversations from main")

logger = logging.getLogger(__name__)

def format_currency(amount: float) -> str:
    return f"RM {amount:,.2f}"


@dataclass
class CampaignState:
    """State management for Perlindungan Combo campaign."""
    current_step: str = "welcome"
    user_data: Dict[str, Any] = field(default_factory=dict)
    age: Optional[int] = None
    package_tier: Optional[int] = None


class PerlindunganComboCampaign:
    """Main handler for Perlindungan Combo campaign."""
    _instance = None

    # Standardized button configurations
    BUTTONS = {
        'welcome': [
            {"label": "📚 Learn More", "value": "learn_more"},
            {"label": "❌ Not Now", "value": "not_now"}
        ],
        'package_selection': [
            {"label": "1️⃣ Silver - Essential Protection", "value": "1"},
            {"label": "2️⃣ Gold - Balanced Protection", "value": "2"},
            {"label": "3️⃣ Platinum - Comprehensive Protection", "value": "3"}
        ],
        'confirmation': [
            {"label": "✅ Yes, Proceed", "value": "yes"},
            {"label": "❌ No, Choose Another Package", "value": "no"}
        ],
        'agent_contact': [
            {"label": "✅ Yes, Contact Me", "value": "yes"},
            {"label": "❌ No Thanks", "value": "no"}
        ],
        'navigation': [
            {"label": "🏠 Main Menu", "value": "main_menu"}
        ]
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def get_buttons(self, button_type: str) -> List[Dict[str, str]]:
        """Get standardized button configuration by type.
        
        Args:
            button_type: Type of buttons to get ('welcome', 'package_selection', 'confirmation', 
                        'agent_contact', 'navigation')
                        
        Returns:
            List of button configurations
        """
        return self.BUTTONS.get(button_type, [])
        
    def create_button_response(self, message: str, button_type: str, **kwargs) -> Dict[str, Any]:
        """Create a standardized button response.
        
        Args:
            message: The message to display
            button_type: Type of buttons to include
            **kwargs: Additional response fields (including next_step, campaign_data, etc.)
            
        Returns:
            Dictionary with response data
        """
        response = {
            "type": "buttons",
            "response": message,
            "content": message,
            "buttons": self.get_buttons(button_type)
        }
        
        # Include any additional fields from kwargs (like next_step, campaign_data, etc.)
        response.update(kwargs)
        
        logger.info(f"[create_button_response] Created response with buttons: {button_type}")
        logger.debug(f"[create_button_response] Full response: {json.dumps(response, indent=2, default=str)}")
        
        return response

    def __init__(self):
        if not hasattr(self, 'initialized') or not self.initialized:
            self.states: Dict[str, CampaignState] = {}
            self.last_active: Dict[str, float] = {}
            self.name = "Perlindungan Combo"
            self.description = "A comprehensive protection plan combining life, medical, and critical illness coverage"
            self.initialized = True
            
            # Package details
            self.package_names = {
                1: "Silver - Essential Protection",
                2: "Gold - Balanced Protection",
                3: "Platinum - Comprehensive Protection"
            }

    def get_state(self, user_id: str) -> CampaignState:
        """Get or create state for a user."""
        if user_id not in self.states:
            self.states[user_id] = CampaignState()
        self.last_active[user_id] = datetime.now().timestamp()
        return self.states[user_id]

    def calculate_combo_tier(self,
    age: int,
    package_tier: int) -> Tuple[Optional[float],
    Optional[float],
     Optional[str]]:
        """
        Calculates premium based on a pre-defined package tier and age band.

        Returns:
            tuple: (annual_premium, monthly_premium, error_message)
        """
        # Pre-defined ANNUAL premiums for each package tier and age band
        package_bands = {
            1: {  # Silver - Essential Protection
                '18-30': 1200,
                '31-40': 1800,
                '41-50': 2700,
                '51-60': 4000
            },
            2: {    # Gold - Balanced Protection
                '18-30': 2000,
                '31-40': 3000,
                '41-50': 4500,
                '51-60': 6500
            },
            3: {  # Platinum - Comprehensive Protection
                '18-30': 3000,
                '31-40': 4500,
                '41-50': 6500,
                '51-60': 9500
            }
        }

        try:
            # Get the package tier
            if package_tier not in package_bands:
                return None, None, "Invalid package tier. Please choose 1, 2, or 3."

            # Determine age band
            if 18 <= age <= 30:
                age_band = '18-30'
            elif 31 <= age <= 40:
                age_band = '31-40'
            elif 41 <= age <= 50:
                age_band = '41-50'
            elif 51 <= age <= 60:
                age_band = '51-60'
            else:
                return None, None, "Combo plans are typically for ages 18-60. Please consult our advisor for alternative options."

            # Get the annual premium for the chosen tier and age band
            annual_premium = package_bands[package_tier][age_band]
            monthly_premium = round(annual_premium / 12, 2)
            return annual_premium, monthly_premium, None

        except Exception as e:
            logger.error(
    f"Error in calculate_combo_tier: {
        str(e)}", exc_info=True)
            return None, None, f"An error occurred while calculating your premium: {
    str(e)}"

    async def send_message(self, message: str, ws: Any = None) -> str:
        """Helper to send text through WebSocket if available."""
        if not message or not isinstance(message, str):
            logger.warning("Attempted to send empty or invalid message")
            return ""

        logger.info(
            f"[PerlindunganCombo] Sending message: {message[:100]}{'...' if len(message) > 100 else ''}")

        if ws:
            try:
                await ws.send_text(json.dumps({
                    "type": "message",
                    "content": message,
                    "is_user": False
                }))
            except Exception as e:
                logger.error(f"Error sending message: {str(e)}", exc_info=True)
        return message

    async def send_buttons(
        self, text: str, buttons: List[Dict[str, str]], ws: Any = None) -> str:
        """Send buttons through WebSocket if available, fallback to text."""
        if not text or not isinstance(text, str):
            logger.warning(
                "Attempted to send buttons with empty or invalid message")
            text = "Please select an option:"

        if not buttons or not isinstance(buttons, list):
            logger.warning("No valid buttons provided, sending as text")
            return await self.send_message(text, ws)

        logger.info(
            f"[PerlindunganCombo] Sending buttons: {text[:100]}{'...' if len(text) > 100 else ''}")

        # Create text fallback first (in case WebSocket fails)
        valid_buttons = []
        for btn in buttons:
            if not isinstance(
    btn, dict) or 'label' not in btn or 'value' not in btn:
                logger.warning(f"Skipping invalid button: {btn}")
                continue
            valid_buttons.append({
                'label': str(btn['label']),
                'value': str(btn['value'])
            })

        if not valid_buttons:
            logger.warning("No valid buttons to send")
            return await self.send_message(text, ws)

        # Create text fallback
        fallback = f"{text}\n" + "\n".join(
            f"{i + 1}. {btn.get('label', 'Option')}"
            for i, btn in enumerate(valid_buttons)
            if isinstance(btn, dict)
        )

        # Try to send via WebSocket if available
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "type": "buttons",
                    "content": text,
                    "buttons": valid_buttons,
                    "is_user": False
                }))
                return text
            except Exception as e:
                logger.error(f"Error sending buttons: {str(e)}", exc_info=True)
                # Fallback to text if WebSocket fails
                return await self.send_message(fallback, ws)

        # If no WebSocket, return text version
        return await self.send_message(fallback, ws)

    def _create_response(self, response_type: str, message: str, buttons: Optional[List[Dict[str, str]]] = None, 
                        next_step: str = None, campaign_data: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a standardized response dictionary."""
        if campaign_data is None:
            campaign_data = {}
            
        response = {
            "type": response_type,
            "response": message,
            "content": message,
            "campaign_data": campaign_data
        }
        
        if buttons is not None:
            response["buttons"] = buttons
        if next_step is not None:
            response["next_step"] = next_step
            
        return response

    def _get_welcome_response(self) -> Dict[str, Any]:
        """Helper method to get welcome message and buttons."""
        welcome_msg = self.get_welcome_message()
        return self.create_button_response(
            message=welcome_msg,
            button_type='welcome',
            next_step='welcome_response'
        )

    def _get_plan_explanation_response(self) -> Dict[str, Any]:
        """Helper method to get plan explanation and next steps."""
        # Only show package selection buttons
        return self._create_response(
            response_type="buttons",
            message=self.get_plan_explanation(),
            buttons=self.get_buttons('package_selection'),
            next_step="after_explanation"
        )

    def _get_plan_estimate_message(
        self, age: int, package_tier: int) -> Tuple[str, float, float, str]:
        """Generate the plan estimate message and return it along with premium details."""
        # Use class-level package_names
        coverage_details = {
            1: "~RM 300k Life, ~RM 200k CI, RM 500k Medical",
            2: "~RM 500k Life, ~RM 300k CI, RM 1m Medical",
            3: "~RM 1m Life, ~RM 500k CI, RM 2m Medical"
        }
        # Calculate premium
        annual_premium, monthly_premium, error = self.calculate_combo_tier(
            age, package_tier)
        if error:
            raise ValueError(error)
        # Build the response message
        response_msg = (
            f"🔍 *Your Combo Plan Estimate*\n"
            f"• Package: {self.package_names.get(package_tier, 'Unknown')}\n"
            f"• Age: {age} years old\n"
            f"• Annual Premium: RM {annual_premium:,.2f}\n"
            f"• Monthly Premium: RM {monthly_premium:,.2f}\n\n"
            f"Includes: {coverage_details.get(package_tier, '')}\n\n"
            "💡 This is a rough estimate. Your final premium depends on your health assessment and exact coverage amounts.\n\n"
            "Would you like our agent to contact you for a more detailed discussion about your protection needs?"
        )

        # Add note for age limits
        if age < 18 or age > 60:
            response_msg += "\n\n⚠️ **Note:** Combo plans are typically for ages 18-60. "
            response_msg += "Our advisor will explain all available options for you."

        # Add contact prompt
        response_msg += "\n\nWould you like an agent to contact you to further discuss the plan?"

        return response_msg, annual_premium, monthly_premium, self.package_names.get(
            package_tier, 'Unknown')

    def calculate_age_from_dob(self, dob_str: str) -> Optional[int]:
        """Calculate age from date of birth string (DD/MM/YYYY format).
        
        Args:
            dob_str: Date of birth in DD/MM/YYYY format
            
        Returns:
            int: Age in years, or None if invalid
        """
        try:
            # Parse the date string into day, month, year
            day, month, year = map(int, dob_str.split('/'))
            # Create date objects
            dob = date(year, month, day)
            today = date.today()
            # Calculate age
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            return age if age >= 0 else None
        except (ValueError, AttributeError, IndexError) as e:
            logger.warning(f"Error calculating age from DOB '{dob_str}': {e}")
            return None
            
    async def process_message(
        self,
        user_id: str,
        message: Union[str, dict],
        ws: Any = None,
        user_data: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Process incoming message and return response.

        Args:
            user_id: Unique identifier for the user
            message: The message from the user, can be string or dict
            ws: Optional WebSocket connection for sending messages
            user_data: Optional dictionary containing user data from main conversation

        Returns:
            dict: Response containing message and next steps
        """
        logger.info(f"[PerlindunganCombo] Processing message: {message}")
        
        # Get or create state for this user
        state = self.get_state(user_id)
        
        # Update state with user data if provided
        if user_data:
            logger.info(f"[PerlindunganCombo] Updating user data: {user_data}")
            state.user_data.update(user_data)
            
            # Update age if available in user_data
            if 'age' in user_data and user_data['age']:
                try:
                    state.age = int(user_data['age'])
                    logger.info(f"[PerlindunganCombo] Updated age from main conversation: {state.age}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[PerlindunganCombo] Invalid age in user_data: {user_data['age']}. Error: {e}")
                    
            # Update name if available
            if 'name' in user_data and user_data['name']:
                state.user_data['name'] = user_data['name']
                logger.info(f"[PerlindunganCombo] Updated name from main conversation: {state.user_data['name']}")
        try:
            logger.info(f"[PerlindunganCombo] Processing message: {message}")
            # Get or create state for this user
            state = self.get_state(user_id)

            # Update state with user data if provided
            if user_data:
                state.user_data.update(user_data)

            # Log the current state and message
            logger.info(f"[PerlindunganCombo] Current step: {state.current_step}")
            logger.info(f"[PerlindunganCombo] User data: {state.user_data}")

            # Extract and normalize message content
            message_content = message.get('text', '') if isinstance(message, dict) else str(message)
            normalized_msg = message_content.lower() if isinstance(message_content, str) else ''

            # Handle welcome message
            if state.current_step == "welcome" or (isinstance(message, str) and message.lower() == 'start'):
                # If user just entered their name, treat as restart
                if 'next_step' in state.user_data and state.user_data['next_step'] == 'get_name':
                    # Accept any input as name and move to DOB step (same as main menu onboarding)
                    state.user_data['name'] = message_content.strip()
                    state.user_data['next_step'] = 'get_dob'
                    state.current_step = "get_dob"
                    return {
                        "type": "message",
                        "response": f"Hi {state.user_data['name']}! What is your date of birth? (DD/MM/YYYY)",
                        "content": f"Hi {state.user_data['name']}! What is your date of birth? (DD/MM/YYYY)",
                        "next_step": "get_dob",
                        "campaign_data": state.user_data
                    }
                # If just restarted, prompt for name
                if state.current_step == "welcome" and not state.user_data.get('name'):
                    state.user_data['next_step'] = 'get_name'
                    return {
                        "type": "message",
                        "response": "Welcome! Let's start again. What is your name?",
                        "content": "Welcome! Let's start again. What is your name?",
                        "next_step": "get_name"
                    }
                # Otherwise, show welcome message
                logger.info("Sending welcome message")
                welcome_msg = self.get_welcome_message()
                state.current_step = "after_welcome"
                return {
                    "type": "buttons",
                    "response": welcome_msg,
                    "content": welcome_msg,
                    "buttons": self.get_buttons('welcome'),
                    "campaign_data": state.user_data,
                    "next_step": "after_welcome"
                }

            # Handle navigation commands
            if isinstance(message, str):
                message_lower = message.lower()
                # Handle main menu
                if message_lower == "main_menu":
                    logger.info("Returning to main menu and restarting campaign for user: %s", user_id)
                    self.states[user_id] = CampaignState(current_step="get_name")
                    # Return a special type for main handler to process campaign reset
                    return {
                        "type": "reset_to_main",
                        "response": "Welcome back to the main menu! What's your name?",
                        "content": "Welcome back to the main menu! What's your name?",
                        "next_step": "get_name",
                    }
                

            # Handle show_benefits_response state
            if state.current_step == "show_benefits_response":
                normalized_msg = message_content.lower() if isinstance(message, str) else ''
                
                if normalized_msg == 'show_estimate':
                    # Check if we have a valid age from user_data
                    try:
                        if hasattr(state, 'user_data') and 'age' in state.user_data and state.user_data['age']:
                            state.age = int(state.user_data['age'])
                            if 18 <= state.age <= 60:
                                logger.info(f"Using age from user_data: {state.age}")
                                state.current_step = 'get_package'
                                return {
                                    "type": "buttons",
                                    "response": f"Great! I see you are {state.age} years old.\n\nPlease select a protection package:",
                                    "content": f"Great! I see you are {state.age} years old.\n\nPlease select a protection package:",
                                    "buttons": self.get_buttons('package_selection'),
                                    "next_step": "get_package"
                                }
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid age in user_data: {e}")
                    
                    # If we get here, either no age was found or it was invalid
                    state.current_step = 'get_age_manually'
                    return {
                        "type": "message",
                        "response": "To calculate your premium, please enter your age (18-60):",
                        "content": "To calculate your premium, please enter your age (18-60):",
                        "next_step": "get_age_manually"
                    }
                elif normalized_msg == "not_now":
                    state.current_step = "end_conversation"
                    response_msg = "Understood. If you have any questions about our protection plans in the future, feel free to ask. Would you like to return to the main menu?"
                    return self.create_button_response(
                        message=response_msg,
                        button_type='navigation',
                        campaign_data=state.user_data,
                        next_step='end_conversation'
                    )
                else:
                    # If we get an unexpected message, show the benefits again
                    benefits_msg = self.get_benefits_message()
                    return {
                        "type": "buttons",
                        "response": benefits_msg,
                        "content": benefits_msg,
                        "buttons": [
                            {"label": "✅ Yes, Show My Estimate", "value": "show_estimate"},
                            {"label": "❌ No Thanks", "value": "not_now"}
                        ],
                        "next_step": "show_benefits_response"
                    }
            
            # Handle after welcome state
            if state.current_step == "after_welcome" or state.current_step == "welcome_response":
                # Normalize message for comparison
                normalized_msg = message_content.lower() if isinstance(message, str) else ''
                
                # Handle benefits display
                if normalized_msg in ['show_benefits', 'learn_more']:
                    benefits_msg = self.get_benefits_message()
                    state.current_step = 'show_benefits_response'
                    return {
                        "type": "buttons",
                        "response": benefits_msg,
                        "content": benefits_msg,
                        "buttons": [
                            {"label": "✅ Yes, Show My Estimate", "value": "show_estimate"},
                            {"label": "❌ No Thanks", "value": "not_now"}
                        ],
                        "next_step": "show_benefits_response"
                    }
                
                # Handle estimate request after showing benefits
                elif normalized_msg == 'show_estimate':
                    # Check if we have a valid age from user_data
                    try:
                        if hasattr(state, 'user_data') and 'age' in state.user_data and state.user_data['age']:
                            state.age = int(state.user_data['age'])
                            if 18 <= state.age <= 60:
                                logger.info(f"Using age from user_data: {state.age}")
                                state.current_step = 'get_package'
                                return {
                                    "type": "buttons",
                                    "response": f"Great! I see you are {state.age} years old.\n\nPlease select a protection package:",
                                    "content": f"Great! I see you are {state.age} years old.\n\nPlease select a protection package:",
                                    "buttons": self.get_buttons('package_selection'),
                                    "next_step": "get_package"
                                }
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid age in user_data: {e}")
                    
                    # If we get here, either no age was found or it was invalid
                    state.current_step = 'get_age_manually'
                    return {
                        "type": "message",
                        "response": "To calculate your premium, please enter your age (18-60):",
                        "content": "To calculate your premium, please enter your age (18-60):",
                        "next_step": "get_age_manually"
                    }
                elif normalized_msg == "not_now" or any(word in normalized_msg for word in ['no', 'n', 'not now', 'later']):
                    state.current_step = "end_conversation"
                    response_msg = "Understood. If you have any questions about our protection plans in the future, feel free to ask. Would you like to return to the main menu?"
                    return self.create_button_response(
                        message=response_msg,
                        button_type='navigation',
                        campaign_data=state.user_data,
                        next_step='end_conversation'
                    )
                
                # Handle agent contact offer
                if state.current_step == "offer_agent_contact":
                    return await self._handle_agent_contact(state, user_id, normalized_msg)
                
                # Handle get_estimate option
                if normalized_msg == "get_estimate" or any(word in normalized_msg for word in ['estimate', 'calculate', 'premium']):
                    state.current_step = "get_age"
                    state.user_data["next_step_after_age"] = "select_package"
                    return {
                        "type": "message",
                        "response": "To calculate your premium, please enter your age (18-60):",
                        "content": "To calculate your premium, please enter your age (18-60):",
                        "campaign_data": state.user_data,
                        "next_step": "get_age"
                    }
                
                # Handle unknown input in after_welcome state
                return self.create_button_response(
                    message="I'm not sure I understand. Please select an option from the buttons above.",
                    button_type='welcome',
                    campaign_data=state.user_data,
                    next_step='after_welcome'
                )

            # Handle after explanation state
            if state.current_step == 'after_explanation':
                if message_content.lower() == 'get_estimate':
                    state.current_step = 'get_age'
                    return {
                        "type": "message",
                        "response": "Please enter your age to get a premium estimate:",
                        "content": "Please enter your age to get a premium estimate:",
                        "next_step": "get_age"
                    }
                elif message_content.isdigit() and int(message_content) in [1, 2, 3]:
                    # User selected a package directly
                    package_choice = int(message_content)
                    state.user_data['package_tier'] = package_choice
                    state.current_step = 'confirm_package'
                    return await self.show_premium_estimate(state, user_id)

            # Handle get_age_manually state - when age is not in user_data
            if state.current_step == "get_age_manually":
                try:
                    # Check if the message is a valid age
                    if message_content.isdigit():
                        age = int(message_content)
                        if 18 <= age <= 60:
                            state.age = age
                            state.current_step = "get_package"
                            return {
                                "type": "buttons",
                                "response": f"Great! I see you are {age} years old.\n\nPlease select a protection package:",
                                "content": f"Great! I see you are {age} years old.\n\nPlease select a protection package:",
                                "buttons": self.get_buttons('package_selection'),
                                "next_step": "get_package"
                            }
                        else:
                            return {
                                "type": "message",
                                "response": "Age must be between 18 and 60. Please enter a valid age:",
                                "content": "Age must be between 18 and 60. Please enter a valid age:",
                                "next_step": "get_age_manually"
                            }
                    else:
                        return {
                            "type": "message",
                            "response": "Please enter a valid number for your age (18-60):",
                            "content": "Please enter a valid number for your age (18-60):",
                            "next_step": "get_age_manually"
                        }
                except (ValueError, TypeError) as e:
                    logger.error(f"Error processing age input: {e}")
                    return {
                        "type": "message",
                        "response": "Sorry, there was an error processing your age. Please enter your age (18-60):",
                        "content": "Sorry, there was an error processing your age. Please enter your age (18-60):",
                        "next_step": "get_age_manually"
                    }
                except Exception as e:
                    logger.error(f"Error in get_age step: {e}")
                    return {
                        "type": "message",
                        "response": "Sorry, there was an error processing your request. Please try again.",
                        "content": "Sorry, there was an error processing your request. Please try again.",
                        "campaign_data": state.user_data,
                        "next_step": "get_package"
                    }
                    
            # Handle restart after name entry or explicit get_name step
            if state.current_step == "welcome" or (isinstance(message, str) and (message.lower() == 'start' or message.lower() == 'get_name')):
                # If just restarted, prompt for name
                if state.current_step == "welcome" and not state.user_data.get('name'):
                    state.user_data['next_step'] = 'get_name'
                    return {
                        "type": "message",
                        "response": "Welcome! Let's start again. What is your name?",
                        "content": "Welcome! Let's start again. What is your name?",
                        "next_step": "get_name"
                    }
                # If user just entered their name, ask for DOB
                if 'next_step' in state.user_data and state.user_data['next_step'] == 'get_name':
                    state.user_data['name'] = message_content.strip()
                    state.user_data['next_step'] = 'get_dob'
                    state.current_step = "get_dob"
                    return {
                        "type": "message",
                        "response": f"Hi {state.user_data['name']}! What is your date of birth? (DD/MM/YYYY)",
                        "content": f"Hi {state.user_data['name']}! What is your date of birth? (DD/MM/YYYY)",
                        "next_step": "get_dob"
                    }
                # If user just entered their DOB, ask for email
                if 'next_step' in state.user_data and state.user_data['next_step'] == 'get_dob':
                    state.user_data['dob'] = message_content.strip()
                    state.user_data['next_step'] = 'get_email'
                    state.current_step = "get_email"
                    return {
                        "type": "message",
                        "response": "What is your email address?",
                        "content": "What is your email address?",
                        "next_step": "get_email"
                    }
                # If user just entered their email, ask for age
                if 'next_step' in state.user_data and state.user_data['next_step'] == 'get_email':
                    state.user_data['email'] = message_content.strip()
                    state.user_data['next_step'] = 'get_age'
                    state.current_step = "get_age"
                    return {
                        "type": "message",
                        "response": "How old are you?",
                        "content": "How old are you?",
                        "next_step": "get_age"
                    }
                # If user just entered their age, continue with the rest of the flow (existing logic)
                if 'next_step' in state.user_data and state.user_data['next_step'] == 'get_age':
                    state.user_data['age'] = message_content.strip()
                    state.current_step = "after_name"
                    # Continue with your existing flow after collecting all info
                    return {
                        "type": "message",
                        "response": f"Thank you! Let's continue.",
                        "content": f"Thank you! Let's continue.",
                        "next_step": "after_name"
                    }
                # Otherwise, do nothing (no welcome message)
                return {}
                
                # Calculate premium
                annual_premium, monthly_premium, error = self.calculate_combo_tier(int(age), package_choice)
                if error:
                    logger.error(f"Error calculating premium: {error}")
                    raise ValueError(f"Error calculating premium: {error}")
                
                logger.info(f"Premium calculated - Annual: {annual_premium}, Monthly: {monthly_premium}")


                #====GOOGLE SHEET INSERTION====
                try:
                    name = state.user_data.get("name", "N/A")
                    dob = state.user_data.get("dob", "")
                    email = state.user_data.get("email", "")
                    primary_concern = state.user_data.get("primary_concern", "")
                    life_stage = state.user_data.get("life_stage", "")
                    dependents = state.user_data.get("dependents", "")
                    existing_coverage = state.user_data.get("existing_coverage", "")
                    premium_budget = state.user_data.get("premium_budget", "")
                    selected_plan = "perlindungan_combo"  # Identifies this campaign in the sheet
                    package_tier_str = str(package_choice)

                    row_data = [
                        name, dob, email, primary_concern, life_stage, dependents,
                        existing_coverage, premium_budget, selected_plan,
                        None, None, None, None, None, None, package_tier_str
                          ]
                    
                    append_row_to_sheet(row_data)
                    logger.info(f"[PERLINDUNGAN_COMBO] Data inserted to Google Sheet: Package Tier={package_tier_str} for user {user_id}")

                except Exception as sheet_error:
                    logger.error(f"[perlindungan_combo] Error inserting data to Google Sheet: {str(sheet_error)}")


                    

                
                # Store premium and package info
                package_name = self.package_names.get(package_choice, f"Package {package_choice}")
                state.user_data["package_choice"] = package_choice
                state.user_data["package_name"] = package_name
                state.user_data["annual_premium"] = annual_premium
                state.user_data["monthly_premium"] = monthly_premium

                # Immediately show contact handling option after package selection
                state.current_step = "follow_up_contact"
                response_msg = (
                    f"Your {package_name} Plan\n\n"
                    f"Estimated Annual Premium: RM {float(annual_premium):,.2f}\n"
                    f"Monthly: RM {float(monthly_premium):,.2f}\n\n"
                    "Would you like one of our agents to contact you with more information about this plan?"
                )
                logger.info(f"[DEBUG] Sending contact handling response after package selection: {response_msg}")
                return self.create_button_response(
                    message=response_msg,
                    button_type='agent_contact',
                    campaign_data=state.user_data,
                    next_step='follow_up_contact'
                )
                
            # Handle confirm_package state
            if state.current_step == "confirm_package":
                try:
                    # After confirming a package, always go to contact handling
                    if message_content.strip().lower() in ["yes", "y", "no", "no thanks", "n", "not now"]:
                        state.current_step = "follow_up_contact"
                        return self.create_button_response(
                            message="Would you like one of our agents to contact you with more information about this plan?",
                            button_type='agent_contact',
                            campaign_data=state.user_data,
                            next_step='follow_up_contact'
                        )
                except Exception as e:
                    logger.error(f"Error in confirm_package step: {e}")
                    return {
                        "type": "message",
                        "response": "Sorry, there was an error processing your request. Please try again.",
                        "content": "Sorry, there was an error processing your request. Please try again.",
                        "campaign_data": state.user_data,
                        "next_step": "confirm_package"
                    }
                    
            # Handle follow_up_contact state
            if state.current_step == "follow_up_contact":
                try:
                    if message_content.strip().lower() in ["yes", "y"]:
                        # User wants to be contacted by an agent
                        return self.create_button_response(
                            message="Thank you! One of our agents will contact you shortly with more information about your selected plan.",
                            button_type='navigation',
                            campaign_data=state.user_data,
                            next_step='end_conversation'
                        )
                    elif message_content.strip().lower() in ["no", "no thanks", "n", "not now"]:
                        # User doesn't want to be contacted, show 'Return to Main Menu' button with next_step 'get_name'
                        return self.create_button_response(
                            message="No problem! If you have any questions later, feel free to ask.",
                            button_type='navigation',
                            campaign_data=state.user_data,
                            next_step='get_name'
                        )
                    else:
                        # Any other response, fallback to navigation
                        return self.create_button_response(
                            message="Is there anything else I can help you with?",
                            button_type='navigation',
                            campaign_data=state.user_data,
                            next_step='end_conversation'
                        )
                except Exception as e:
                    logger.error(f"Error in follow_up_contact step: {e}")
                    return {
                        "type": "message",
                        "response": "Sorry, there was an error processing your request. Please try again.",
                        "content": "Sorry, there was an error processing your request. Please try again.",
                        "campaign_data": state.user_data,
                        "next_step": "follow_up_contact"
                    }
                
            # Handle show_estimate state
            if state.current_step == "show_estimate":
                try:
                    # Get the selected package and age
                    package_choice = state.user_data.get("package_choice")
                    age = state.user_data.get("age", 30)  # Default to 30 if not set
                    
                    if not package_choice:
                        # If no package selected, go back to package selection
                        state.current_step = "get_package"
                        return self.create_button_response(
                            message="Please select a protection package:",
                            button_type='package_selection',
                            campaign_data=state.user_data,
                            next_step='get_package'
                        )
                    
                    # Get package details and update user data
                    response_msg, annual_premium, monthly_premium, package_name = self._get_plan_estimate_message(
                        age, package_choice)
                    state.user_data["package_name"] = package_name
                    state.user_data["annual_premium"] = annual_premium
                    state.user_data["monthly_premium"] = monthly_premium
                    
                    # Move to confirm_package state
                    state.current_step = "confirm_package"
                    
                    # Ask for confirmation
                    return self.create_button_response(
                        message=f"{response_msg}\n\nWould you like to proceed with this plan?",
                        button_type='confirmation',
                        campaign_data=state.user_data,
                        next_step='confirm_package'
                    )
                except Exception as e:
                    logger.error(f"Error in show_estimate step: {e}")
                    return {
                        "type": "message",
                        "response": "❌ Sorry, there was an error processing your request. Please try again.",
                        "content": "❌ Sorry, there was an error processing your request. Please try again.",
                        "campaign_data": state.user_data,
                        "next_step": "show_estimate"
                    }
                    
            # Handle follow_up_quote state
            if state.current_step == "follow_up_quote":
                try:
                    package_name = state.user_data.get('package_name', 'selected package')
                    normalized_msg = message_content.lower()
                    
                    # Check if the message contains any 'yes' indicators
                    if any(word in normalized_msg for word in ['yes', 'y', 'ya', 'yeah', 'contact']):
                        # User wants to be contacted
                        response_msg = f"Our agent will contact you soon. You should receive an email with information regarding your {package_name} plan."
                        # Reset the conversation
                        self.states[user_id] = CampaignState()
                        return {
                            "type": "message",
                            "response": response_msg,
                            "content": response_msg,
                            "campaign_data": state.user_data,
                            "next_step": "end_conversation"
                        }
                    else:
                        # Handle other responses
                        return {
                            "type": "message",
                            "response": "I'm sorry, I didn't understand. Would you like me to have an agent contact you about your plan? (yes/no)",
                            "content": "I'm sorry, I didn't understand. Would you like me to have an agent contact you about your plan? (yes/no)",
                            "campaign_data": state.user_data,
                            "next_step": "follow_up_quote"
                        }
                except Exception as e:
                    logger.error(f"Error in follow_up_quote step: {e}")
                    return {
                        "type": "message",
                        "response": "❌ Sorry, there was an error processing your request. Please try again.",
                        "content": "❌ Sorry, there was an error processing your request. Please try again.",
                        "campaign_data": state.user_data,
                        "next_step": "follow_up_quote"
                    }
            
            # Handle get_age state
            elif state.current_step == "get_age":
                # First try to get age from the provided user_data
                if user_data and 'age' in user_data and user_data['age']:
                    try:
                        age = int(user_data['age'])
                        if 0 <= age <= 120:
                            state.user_data["age"] = age
                            state.current_step = "get_package"
                            return self.create_button_response(
                                message=f"Thank you! I see you are {age} years old.\n\nPlease select a protection package:",
                                button_type='package_selection',
                                campaign_data=state.user_data,
                                next_step='get_package'
                            )
                    except (ValueError, TypeError):
                        pass  # Invalid age format, fall through to manual input
                    
                    # Fallback to checking main conversation state (legacy support)
                    try:
                        from main import active_conversations
                        for conv_state in active_conversations.values():
                            if hasattr(conv_state, 'user_data') and 'age' in conv_state.user_data:
                                age = conv_state.user_data['age']
                                if 0 <= int(age) <= 120:
                                    state.user_data["age"] = int(age)
                                    state.current_step = "get_package"
                                    return self.create_button_response(
                                        message=f"Thank you! I see you are {age} years old.\n\nPlease select a protection package:",
                                        button_type='package_selection',
                                        campaign_data=state.user_data,
                                        next_step='get_package'
                                    )
                    except Exception as e:
                        logger.warning(f"Couldn't get age from conversation state: {e}")
                    
                    # If we get here, we need to ask for age
                    return {
                        "type": "message",
                        "response": "Please enter your age (0-120) to continue:",
                        "content": "Please enter your age (0-120) to continue:",
                        "campaign_data": state.user_data,
                        "next_step": "get_age"
                    }
            # Handle package selection in get_package state
            if state.current_step == "get_package" and message_content.isdigit() and int(message_content) in [1, 2, 3]:
                package_choice = int(message_content)
                state.user_data["package_tier"] = package_choice
                # Calculate premium
                age = state.age if state.age else int(state.user_data.get("age", 30))
                annual_premium, monthly_premium, error = self.calculate_combo_tier(age, package_choice)
                package_name = self.package_names.get(package_choice, f"Package {package_choice}")
                state.user_data["package_choice"] = package_choice
                state.user_data["package_name"] = package_name
                state.user_data["annual_premium"] = annual_premium
                state.user_data["monthly_premium"] = monthly_premium
                state.current_step = "follow_up_contact"
                response_msg = (
                    f"Your {package_name} Plan\n\n"
                    f"Estimated Annual Premium: RM {float(annual_premium):,.2f}\n"
                    f"Monthly: RM {float(monthly_premium):,.2f}\n\n"
                    "Would you like one of our agents to contact you with more information about this plan?"
                )
                logger.info(f"[DEBUG] Sending contact handling response after package selection: {response_msg}")
                return self.create_button_response(
                    message=response_msg,
                    button_type='agent_contact',
                    campaign_data=state.user_data,
                    next_step='follow_up_contact'
                )
            # Log the unexpected state and message for debugging
            logger.error(f"[PerlindunganCombo] Fallback reached. State: {state.current_step}, Message: {message_content}, User Data: {state.user_data}")
            response_msg = (
                "Sorry, I couldn't understand your last input or something went wrong. "
                f"(State: {state.current_step}, Message: '{message_content}')\n"
                "Please try again or type 'main_menu' to restart."
            )
            return {
                "type": "message",
                "response": response_msg,
                "content": response_msg,
                "campaign_data": state.user_data,
                "next_step": "welcome"
            }
        except Exception as e:
            logger.error(f"Error in process_message: {e}", exc_info=True)
            return {
                "type": "message",
                "response": "❌ An error occurred while processing your request. Please try again.",
                "content": "❌ An error occurred while processing your request. Please try again.",
                "campaign_data": {},
                "next_step": "welcome"
            }

    async def show_premium_estimate(self, state, user_id: str) -> dict:
        """Show premium estimate based on user data."""
        try:
            # Get user data
            age = state.user_data.get('age')
            package_tier = state.user_data.get('package_tier')
            
            if not age or not package_tier:
                return {
                    "type": "message",
                    "response": "❌ Missing required information. Please start over.",
                    "content": "❌ Missing required information. Please start over.",
                    "next_step": "welcome"
                }
            
            # Calculate premium based on age and package tier
            response_msg, annual_premium, monthly_premium, package_name = self._get_plan_estimate_message(age, package_tier)
            
            # Store premium information in user data
            state.user_data.update({
                'annual_premium': annual_premium,
                'monthly_premium': monthly_premium,
                'package_name': package_name
            })
            
            # Update state to show contact offer
            state.current_step = "offer_agent_contact"
            
            # Add contact prompt
            response_msg += "\n\nWould you like an agent to contact you to further discuss the plan?"
            
            return self.create_button_response(
                message=response_msg,
                button_type='agent_contact',
                campaign_data=state.user_data,
                next_step='follow_up_contact'
            )

        except Exception as e:
            logger.error(f"Error in show_premium_estimate step: {e}")
            return {
                "type": "message",
                "response": "❌ Sorry, there was an error processing your request. Please try again.",
                "content": "❌ Sorry, there was an error processing your request. Please try again.",
                "next_step": "show_estimate"
            }

    def get_welcome_message(self) -> str:
        """Return the welcome message for this campaign."""
        return """*🛡️ Welcome to Perlindungan Combo - Your Complete Protection Solution*

I can help you find the perfect protection plan that combines:
• Life Insurance
• Critical Illness Coverage
• Medical Protection
• Accident Coverage

All in one simple, affordable package. Would you like to learn more about the benefits?"""

    def get_benefits_message(self) -> str:
        """Return the benefits message for this campaign."""
        return """💎 *Benefits of Combo Protection:*

• All-in-one coverage: Life, Medical, Critical Illness, Accident
• Single premium payment - simpler to manage
• Better value than buying separate policies
• No coverage gaps - complete protection
• Guaranteed insurability for all coverage types

Would you like to get a quick estimate of your premium based on your age and desired coverage?"""

    async def _handle_agent_contact(self, state: CampaignState, user_id: str, message: str) -> Dict[str, Any]:
        """Handle agent contact preference and navigation options."""
        if message == "contact_agent":
            # Update state and confirm contact
            state.current_step = "contact_confirmed"
            return self.create_button_response(
                message="Great! Our agent will contact you soon. You will also receive an email about further information on the plans we offer.",
                button_type='navigation',
                campaign_data=state.user_data,
                next_step='contact_confirmed'
            )
        else:  # no_contact
            state.current_step = "end_options"
            return self.create_button_response(
                message="No problem! Feel free to reach out if you have any questions later. What would you like to do next?",
                button_type='navigation',
                campaign_data=state.user_data,
                next_step='end_options'
            )

    def _get_welcome_response(self) -> Dict[str, Any]:
        """Helper method to get welcome message and buttons."""
        welcome_msg = self.get_welcome_message()
        return self.create_button_response(
            message=welcome_msg,
            button_type='welcome',
            next_step='welcome_response'
        )

    def get_initial_message(self, user_id: str) -> dict:
        """Get the initial welcome message with buttons."""
        welcome_response = self._get_welcome_response()
        welcome_response.update({
            "message": welcome_response["response"],
            "text": welcome_response["response"],
            "is_user": False,
            "timestamp": datetime.now().isoformat()
        })
        return welcome_response

    def get_plan_explanation(self) -> str:
        """Return the explanation of the combo protection plan."""
        return (
            "💎 *Benefits of Combo Protection:*\n\n"
            "• **All-in-one coverage:** Life, Medical, Critical Illness, Accident\n"
            "• **Single premium payment** - simpler to manage\n"
            "• **Better value** than buying separate policies\n"
            "• **No coverage gaps** - complete protection\n"
            "• **Guaranteed insurability** for all coverage types\n\n"
            "Would you like to get a quick estimate of your premium based on your age and desired coverage?"
        )

# Create a singleton instance
perlindungan_combo_campaign = PerlindunganComboCampaign()
# Alias for backward compatibility with main.py
perlindungan_combo_campaign_instance = perlindungan_combo_campaign

# For testing the campaign directly
if __name__ == "__main__":
    import asyncio

    async def test_campaign():
        """Test the campaign directly."""
        campaign = perlindungan_combo_campaign
        print(f"Testing campaign: {campaign.name}")
        
        # Test welcome message
        print("\n=== Testing welcome message ===")
        welcome = campaign.get_initial_message("test_user")
        print(welcome)
        
        # Test processing a response
        print("\n=== Testing response processing ===")
        response = await campaign.process_message("test_user", "get_estimate")
        print(response)
        
        # Test age input
        print("\n=== Testing age input ===")
        response = await campaign.process_message("test_user", "30")
        print(response)
        
        # Test package selection
        print("\n=== Testing package selection ===")
        try:
            response = await campaign.process_message("test_user", "1")
            print(response)
        except Exception as e:
            print(f"Error: {e}")
        
        print("\nTest completed!")

    # Run the test
    asyncio.run(test_campaign())