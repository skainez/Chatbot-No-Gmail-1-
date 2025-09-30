from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import json
import asyncio
from datetime import datetime
from Google_Sheet import append_row_to_sheet

logger = logging.getLogger(__name__)

def format_currency(amount: float) -> str:
    return f"RM {amount:,.2f}"

@dataclass
class TabungPerubatanState:
    """State management for Tabung Perubatan campaign."""
    current_step: str = "welcome"
    user_data: Dict[str, Any] = field(default_factory=dict)
    age: Optional[int] = None
    coverage_level: Optional[int] = None
    name: Optional[str] = None
    # phone: Optional[str] = None  # Removed phone field
    
class TabungPerubatanCampaign:
    """Main handler for Tabung Perubatan campaign."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            self.states: Dict[str, TabungPerubatanState] = {}
            self.last_active: Dict[str, float] = {}
            self.name = "Tabung Perubatan"
            self.description = "Comprehensive medical coverage with cashless hospital admissions and extensive benefits"
            self.initialized = True
    
    def get_state(self, user_id: str) -> TabungPerubatanState:
        """Get or create state for a user."""
        if user_id not in self.states:
            self.states[user_id] = TabungPerubatanState()
        self.last_active[user_id] = datetime.now().timestamp()
        return self.states[user_id]
    
    def get_welcome_message(self) -> str:
        """Return the welcome message for the campaign."""
        return (
            "🏥 *Welcome to Tabung Perubatan!* 🏥\n\n"
            "Let's talk about something important: your health and your savings.\n\n"
            "A single hospital stay can cost tens of thousands of Ringgit. "
            "This plan is a 'Medical Fund' that protects your life savings from "
            "being wiped out by unexpected medical bills."
        )
    
    def get_plan_explanation(self) -> str:
        """Return the explanation of the medical plan."""
        return (
            "🌟 *What is Tabung Perubatan?*\n\n"
            "It's your personal financial safety net for healthcare. Think of it as a "
            '"Medical Card" that gives you:\n\n'
            "• **Cashless Hospital Admission:** Walk into any of our panel hospitals, focus on getting better. "
            "We settle the bill directly. No large upfront payments.\n"
            "• **High Annual Limit:** Coverage from RM 100,000 to over RM 1,000,000 per year "
            "for surgeries, ICU, room & board, and medication.\n"
            "• **Protection for Your Savings:** Shields your family's finances from the shock "
            "of a major medical event. Your savings remain for your dreams, not hospital bills."
        )
    
    def estimate_medical_premium(self, age: int, coverage_level: int) -> tuple[float, str]:
        """Estimate medical premium based on age and coverage level."""
        try:
            # Base premium by age group
            if age <= 17:  # Children
                base_premium = 80.0
            elif age <= 60:  # Adults
                base_premium = 120.0
            else:  # Seniors
                base_premium = 350.0
            
            # Adjust by coverage level
            if coverage_level == 1:  # Basic
                multiplier = 1.0
            elif coverage_level == 2:  # Medium
                multiplier = 2.0
            else:  # Comprehensive
                multiplier = 3.5
                
            # Add age adjustment
            if age > 40:
                age_adjustment = (age - 40) * 2.5
            else:
                age_adjustment = 0
                
            premium = (base_premium * multiplier) + age_adjustment
            return round(premium, 2), ""
            
        except Exception as e:
            logger.error(f"Error calculating premium: {str(e)}")
            return 0.0, "Unable to calculate premium at this time"
    
    def _get_welcome_response(self) -> Dict[str, Any]:
        """Helper method to get welcome message and buttons."""
        welcome_message = self.get_welcome_message()
        return {
            "type": "message",
            "text": welcome_message + "\n\nWould you like to know more about this medical coverage plan?",
            "content": welcome_message + "\n\nWould you like to know more about this medical coverage plan?",
            "buttons": [
                {"label": "✅ Yes, tell me more", "value": "yes"},
                {"label": "❌ Not now, thanks", "value": "no"}
            ],
            "next_step": "check_interest_response"
        }
        
    def _get_estimation_question(self, state) -> Dict[str, Any]:
        """Helper method to get estimation question with buttons."""
        question = "Would you like to see an estimation of the coverage you can receive?"
        # Update the state to expect a response to the estimation question
        state.current_step = "handle_estimation_response"
        return {
            "type": "buttons",
            "text": question,
            "content": question,
            "buttons": [
                {"label": "✅ Yes, show me an estimate", "value": "yes_estimate"},
                {"label": "❌ Not now, thanks", "value": "no"}
            ]
        }
    
    async def process_message(
        self,
        user_id: str,
        message: Union[str, dict],
        ws: Any = None,
        user_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process incoming message and return response.
        
        Args:
            user_id: Unique identifier for the user
            message: The message from the user, can be string or dict
            ws: Optional WebSocket connection for sending messages
            user_data: Optional dictionary containing user data from main conversation
            
        Returns:
            dict: Response containing message and next steps
        """
        try:
            logger.info(f"[TabungPerubatan] Processing message: {message}")
            # Get or create state for this user
            state = self.get_state(user_id)

            # Update state with user data if provided
            if user_data:
                state.user_data.update(user_data)
                # Update age if available in user_data
                if 'age' in user_data and user_data['age']:
                    try:
                        state.age = int(user_data['age'])
                        logger.info(f"[TabungPerubatan] Updated age from main conversation: {state.age}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[TabungPerubatan] Invalid age in user_data: {user_data['age']}. Error: {e}")
                
                # Update name if available
                if 'name' in user_data and user_data['name']:
                    state.name = user_data.get('name')
                    logger.info(f"[TabungPerubatan] Updated name from main conversation: {state.name}")

            # Extract message content if it's a dictionary
            message_content = message.get('text', '') if isinstance(message, dict) else str(message)
            normalized_msg = message_content.lower() if isinstance(message_content, str) else ''
            
            # Log the current state and message
            logger.info(f"[TabungPerubatan] Current step: {state.current_step}")
            logger.info(f"[TabungPerubatan] User data: {state.user_data}")
            logger.info(f"[TabungPerubatan] User age: {state.age}")
            logger.info(f"[TabungPerubatan] Message: '{message}'")
            
            # Log the message content in detail
            if normalized_msg == "start":
                logger.info("[TabungPerubatan] Received 'start' command")
            elif normalized_msg in ["yes", "no"]:
                logger.info(f"[TabungPerubatan] Received button click: {normalized_msg}")
            
            # Initialize response with default values
            response = {
                "type": "message",
                "response": "",
                "content": "",
                "campaign_data": state.user_data,
                "next_step": state.current_step
            }
            
            # Clean and normalize the message
            message = message.strip().lower() if message else ""
            
            # Handle special commands
            if message in ["restart", "main_menu"]:
                # Do NOT reset campaign state, just signal main.py to reset to get_name
                return {
                    "type": "reset_to_main",
                    "response": "Returning to main menu...",
                    "content": "Returning to main menu...",
                    "reset_to_main": True
                }
            
            # Handle welcome state
            if state.current_step == "welcome" or not state.current_step:
                welcome_response = self._get_welcome_response()
                state.current_step = welcome_response.get("next_step", "check_interest_response")
                return welcome_response
            
            # Handle response to interest check
            elif state.current_step == "check_interest_response":
                # Check for button click value first
                if message == "yes" or any(word in message for word in ['yes', 'y', 'ya', 'yeah', 'sure', 'ok']):
                    explanation = self.get_plan_explanation()
                    
                    # Update the state first
                    state.current_step = "handle_estimation_response"
                    
                    # Combine explanation and estimation question into one message
                    combined_text = f"{explanation}\n\nWould you like to see an estimation of the coverage you can receive?"
                    
                    # Return the response with buttons
                    return {
                        "type": "buttons",
                        "text": combined_text,
                        "content": combined_text,
                        "buttons": [
                            {"label": "✅ Yes, show me an estimate", "value": "yes_estimate"},
                            {"label": "❌ Not now, thanks", "value": "no"}
                        ],
                        "next_step": "handle_estimation_response"
                    }
                elif message == "estimate":  # Directly handle estimate as well
                    # Skip age request since we get it from main conversation
                    state.current_step = "get_coverage_level"
                    
                    # Prepare the message with the user's age if available
                    age_info = f"I see you're {state.age} years old. " if state.age else ""
                    
                    return {
                        "type": "buttons",
                        "content": f"{age_info}Please select your desired coverage level:",
                        "next_step": "get_coverage_level",
                        "buttons": [
                            {"label": "Basic (RM100k annual limit)", "value": "1"},
                            {"label": "Medium (RM500k annual limit)", "value": "2"},
                            {"label": "Comprehensive (RM1M+ annual limit)", "value": "3"}
                        ]
                    }
                elif message == "no" or any(word in message for word in ['no', 'n', 'not now', 'later']):
                    state.current_step = "end_conversation"
                    return {
                        "type": "buttons",
                        "content": "Understood. If you have any questions about medical coverage in the future, feel free to ask. Stay healthy!",
                        "next_step": "end_conversation",
                        "buttons": [
                            {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                else:
                    # If we get an unexpected response, just return the welcome response without changing the state
                    return self._get_welcome_response()
            
            # Ask for estimation (handled in check_interest_response now)
            elif state.current_step == "ask_estimation":
                # Just in case we get here, redirect to welcome
                state.current_step = "welcome"
                return self._get_welcome_response()
                
            # Handle response to estimation question
            elif state.current_step == "handle_estimation_response":
                # Debug log the received message
                logger.info(f"[TabungPerubatan] Handling estimation response. Message: '{message}', Type: {type(message)}")
                
                # Check for button click value first
                if (isinstance(message, str) and 
                    (message == "yes_estimate" or 
                     message == "estimate" or 
                     any(word in message.lower() for word in ['yes', 'y', 'ya', 'sure', 'ok']))):
                    
                    logger.info("[TabungPerubatan] User requested estimate. Moving to coverage level selection.")
                    state.current_step = "get_coverage_level"
                    
                    # Prepare the message with the user's age if available
                    age_info = f"I see you're {state.age} years old. " if state.age else ""
                    
                    return {
                        "type": "buttons",
                        "content": f"{age_info}Please select your desired coverage level:",
                        "next_step": "get_coverage_level",
                        "buttons": [
                            {"label": "🏥 Basic (RM100k/year)", "value": "1"},
                            {"label": "🏥🏥 Medium (RM500k/year)", "value": "2"},
                            {"label": "🏥🏥🏥 Comprehensive (RM1M+/year)", "value": "3"}
                        ]
                    }
                elif message == "no" or any(word in message for word in ['no', 'n', 'not now', 'later']):
                    state.current_step = "end_conversation"
                    return {
                        "type": "buttons",
                        "content": "Understood. If you have any questions about medical coverage in the future, feel free to ask. Stay healthy!",
                        "next_step": "end_conversation",
                        "buttons": [
                            {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                else:
                    # If we get an unexpected response, ask again
                    return self._get_estimation_question()
            
            # Get coverage level
            elif state.current_step == "get_coverage_level":
                try:
                    # Extract number from message or check button value
                    coverage_level = None
                    if message.isdigit():
                        coverage_level = int(message)
                    elif any(word in message.lower() for word in ['basic', '100k', '100k']):
                        coverage_level = 1
                    elif any(word in message.lower() for word in ['medium', '500k', '500k']):
                        coverage_level = 2
                    elif any(word in message.lower() for word in ['comprehensive', '1m', '1m+', '1m+']):
                        coverage_level = 3
                    
                    if coverage_level not in [1, 2, 3]:
                        raise ValueError("Please select a valid coverage level")
                    
                    state.coverage_level = coverage_level
                    
                    # Calculate premium
                    premium, error = self.estimate_medical_premium(state.age, coverage_level)
                    
                    if error:
                        return {
                            "type": "message",
                            "content": f"Sorry, there was an error calculating your premium: {error}",
                            "next_step": "get_coverage_level"
                        }
                    
                    #Insert data Google Sheet
                    try:
                        name = state.user_data.get("name", "N/A")
                        dob = state.user_data.get("dob", "")
                        email = state.user_data.get("email", "")
                        primary_concern = state.user_data.get("primary_concern", "")
                        life_stage = state.user_data.get("life_stage", "")
                        dependents = state.user_data.get("dependents", "")
                        existing_coverage = state.user_data.get("existing_coverage", "")
                        premium_budget = state.user_data.get("premium_budget", "")
                        selected_plan = "tabung_perubatan"

                        coverage_level_str = str(coverage_level)
                    

                        row_data = [
                            name, dob, email, primary_concern, life_stage, dependents,
                            existing_coverage, premium_budget, selected_plan,
                            None, None, None, None, None,  # SKIP 6 LAJUR after selected_plan
                            coverage_level_str # Data perubatan: Coverage level & umur (mirroring warisan structure but with 6 skips)
                        ]

                        append_row_to_sheet(row_data)
                        logger.info(f"[TABUNG_PERUBATAN] Data perubatan dimasukkan ke Google Sheet: Coverage Level={coverage_level_str} untuk user {user_id}")

                    except Exception as sheet_error:
                        logger.error(f"[tabung_perubatan] Error inserting perubatan data to Google Sheet: {str(sheet_error)}")

                    # Format premium with 2 decimal places
                    formatted_premium = f"RM{premium:,.2f}"
                    
                    # Get coverage amount based on level
                    coverage_level_names = {1: "Basic", 2: "Medium", 3: "Comprehensive"}
                    coverage_amounts = {
                        1: "RM100,000",
                        2: "RM500,000",
                        3: "RM1,000,000"
                    }
                    
                    response_msg = (
                        f"Based on your age ({state.age}) and selected coverage level ({coverage_level_names[coverage_level]}):\n\n"
                        f"• Estimated Monthly Premium: {formatted_premium}\n"
                        f"• Annual Coverage: {coverage_amounts[coverage_level]}"
                    )
                    
                    # Format premium with 2 decimal places
                    formatted_premium = f"RM{premium:,.2f}"
                    
                    # Get coverage amount based on level
                    coverage_level_names = {1: "Basic", 2: "Medium", 3: "Comprehensive"}
                    coverage_amounts = {
                        1: "RM100,000",
                        2: "RM500,000",
                        3: "RM1,000,000"
                    }
                    
                    response_msg = (
                        f"Based on your age ({state.age}) and selected coverage level ({coverage_level_names[coverage_level]}):\n\n"
                        f"• Estimated Monthly Premium: {formatted_premium}\n"
                        f"• Annual Coverage: {coverage_amounts[coverage_level]}"
                    )
                    
                    # Add note for seniors
                    if state.age and state.age >= 61:
                        response_msg += (
                            "\n\n⚠️ **Note for Senior Applicants:**\n"
                            "Medical insurance for seniors may have certain conditions. "
                            "Our advisor will explain all details and available options."
                        )
                    
                    # Update the state
                    state.current_step = "offer_agent_contact"
                    
                    return {
                        "type": "buttons",
                        "content": f"{response_msg}\n\nWould you like an agent to contact you to further discuss the plan?",
                        "next_step": "offer_agent_contact",
                        "buttons": [
                            {"label": "✅ Yes, contact me", "value": "contact_agent"},
                            {"label": "❌ No thanks", "value": "no_contact"}
                        ]
                    }
                    
                except ValueError as e:
                    buttons = [
                        {"label": "Basic (~RM 100K/year)", "value": "1"},
                        {"label": "Medium (~RM 500K/year)", "value": "2"},
                        {"label": "Comprehensive (RM 1M+/year)", "value": "3"}
                    ]
                    
                    return {
                        "type": "buttons",
                        "content": f"Please select a valid coverage level.\n\n" + "\n".join([f"{i}. {b['label']}" for i, b in enumerate(buttons, 1)]),
                        "buttons": buttons,
                        "next_step": "get_coverage_level"
                    }
            
            # Handle agent contact preference and navigation options
            elif state.current_step == "offer_agent_contact":
                message_lower = message.lower().strip()
                
                if message_lower == "contact_agent":
                    # Skip phone number collection and directly confirm
                    state.current_step = "contact_confirmed"
                    return {
                        "type": "buttons",
                        "content": "Great! Our agent will contact you soon. You will also receive an email about further information on the plans we offer.",
                        "next_step": "contact_confirmed",
                        "buttons": [
                            {"label": "🏠 Main Menu", "value": "main_menu"}
                        ]
                    }
                elif message_lower == "no_contact":
                    state.current_step = "end_options"
                    return {
                        "type": "buttons",
                        "content": "Thank you for your interest in Tabung Perubatan! If you wish to return to the main menu, click below.",
                        "next_step": "end_options",
                        "buttons": [
                            {"label": "🏠 Main Menu", "value": "main_menu"}
                        ]
                    }
                elif message_lower == "other_plans":
                    # Show other available plans
                    state.current_step = "show_plans"
                    return {
                        "type": "buttons",
                        "content": "Here are our other available plans that might interest you:",
                        "next_step": "show_plans",
                        "buttons": [
                            {"label": "💰 Tabung Warisan", "value": "tabung_warisan"},
                            {"label": "👨‍👩‍👧‍👦 Masa Depan Anak Kita", "value": "masa_depan_anak_kita"},
                            {"label": "💼 Satu Gaji Satu Harapan", "value": "satu_gaji"},
                            {"label": "🏠 Main Menu", "value": "main_menu"}
                        ]
                    }
                elif message_lower == "main_menu":
                        # Clear user state so main.py will restart from get_name
                        if user_id in self.states:
                            del self.states[user_id]
                        return {
                            "type": "reset_to_main",
                            "response": "Returning to main menu...",
                            "content": "Returning to main menu...",
                            "reset_to_main": True
                        }
                elif message_lower == "restart":
                    # Signal main.py to reset and start from get_name
                    return {
                        "type": "reset_to_main",
                        "response": "Returning to main menu...",
                        "content": "Returning to main menu...",
                        "reset_to_main": True
                    }
            
            # Get contact information
            elif state.current_step == "get_contact_info":
                # Only collect name, skip phone number
                import re
                name = re.sub(r'\d+', '', message).strip()
                if not name:
                    return {
                        "type": "message",
                        "content": "Please provide a valid name.",
                        "next_step": "get_contact_info"
                    }
                state.name = name
                state.current_step = "end_conversation"
                logger.info(f"Lead generated: {state.name}, Age: {state.age}, Coverage Level: {state.coverage_level}")
                return {
                    "type": "message",
                    "content": (
                        f"Thank you, {state.name}! One of our agents will contact you shortly to discuss your medical coverage options and provide an exact quote.\n\n"
                        "Have a great day! 😊"
                    ),
                    "next_step": "end_conversation"
                }
            
            # End of conversation
            elif state.current_step == "end_conversation":
                return {
                    "type": "message",
                    "content": "Thank you for your interest in Tabung Perubatan. Have a great day!",
                    "response": "Thank you for your interest in Tabung Perubatan. Have a great day!",
                    "next_step": "end_conversation"
                }
            
            # Default response for unknown state
            else:
                logger.warning(f"Unknown state: {state.current_step}")
                state.current_step = "welcome"
                response = await self.process_message(user_id, "start", ws)
            
            # Ensure we always have a valid response
            if not response.get('response'):
                response['response'] = response.get('content', "I'm not sure how to respond to that. Let's start over.")
                response['next_step'] = 'welcome'
                state.current_step = 'welcome'
            
            # Ensure we have both response and content
            if 'content' not in response and 'response' in response:
                response['content'] = response['response']
            
            # Always include campaign_data in the response
            response['campaign_data'] = state.user_data
            
            logger.info(f"Returning response: {response}")
            return response
                
        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}", exc_info=True)
            return {
                "type": "message",
                "content": "Sorry, an error occurred. Let's start over.",
                "response": "Sorry, an error occurred. Let's start over.",
                "campaign_data": {},
                "next_step": "welcome"
            }

# Create a singleton instance
tabung_perubatan_campaign = TabungPerubatanCampaign()

# Alias for backward compatibility with main.py
tabung_perubatan_campaign_instance = tabung_perubatan_campaign

# For testing the campaign directly
if __name__ == "__main__":
    class MockWebSocket:
        def __init__(self):
            self.messages = []
            
        async def send_text(self, message: str):
            self.messages.append(message)
            print(f"BOT: {message}")
    
    async def test_campaign():
        campaign = TabungPerubatanCampaign()
        ws = MockWebSocket()
        user_id = "test_user"
        
        # Reset state
        campaign.states[user_id] = TabungPerubatanState()
        
        # Test the conversation flow
        responses = [
            "start",  # Welcome message
            "yes",    # Show me more
            "yes",    # Show me an estimate
            "35",     # Age
            "2",      # Coverage level (Medium)
            "yes",    # Connect with agent
            "John Doe", # Name
            "0123456789" # Phone
        ]
        
        for msg in responses:
            print(f"\nYOU: {msg}")
            response = await campaign.process_message(user_id, msg, ws)
            if response:
                await ws.send_text(response.get("response", "No response"))
                
    asyncio.run(test_campaign())
