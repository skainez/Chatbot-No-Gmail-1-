from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging
from datetime import datetime
import json
import re
import asyncio
from Google_Sheet import append_row_to_sheet

logger = logging.getLogger(__name__)

def format_currency(amount: float) -> str:
    """Format amount as currency string."""
    return f"RM {amount:,.2f}"

@dataclass
class TabungWarisanState:
    """State management for Tabung Warisan campaign."""
    current_step: str = "welcome"
    user_data: Dict[str, Any] = field(default_factory=dict)
    user_name: str = ""
    user_age: int = 0
    desired_legacy: float = 0.0
    last_active: datetime = field(default_factory=datetime.now)
    welcome_shown: bool = False
    def reset(self):
        """Reset the state to initial values."""
        self.__init__()
    
    def calculate_warisan_premium_estimation(self, legacy_amount: float, age: int) -> float:
        """Estimate premium based on legacy amount and age."""
        if age <= 35:
            base_factor = 30
        elif age <= 45:
            base_factor = 40
        else:
            base_factor = 55
        return (legacy_amount / 1000) * base_factor

class TabungWarisanCampaign:
    """Main handler for Tabung Warisan campaign."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            self.states: Dict[str, TabungWarisanState] = {}
            self.last_active: Dict[str, float] = {}
            self._name = "Tabung Warisan"
            self._description = "Legacy planning to secure your family's future"
            self.initialized = True
    
    @property
    def name(self) -> str:
        """Return the name of the campaign."""
        return self._name
    
    @property
    def description(self) -> str:
        """Return the description of the campaign."""
        return self._description
    
    # ===== State Management =====
    def get_state(self, user_id: str) -> TabungWarisanState:
        """Get or create state for a user."""
        if user_id not in self.states:
            self.states[user_id] = TabungWarisanState()
        self.last_active[user_id] = datetime.now().timestamp()
        return self.states[user_id]
    
    async def cleanup_old_states(self, max_age_seconds: int = 3600):
        """Remove inactive user states."""
        now = datetime.now().timestamp()
        to_remove = [
            uid for uid, last_active in self.last_active.items()
            if now - last_active > max_age_seconds
        ]
        for uid in to_remove:
            self.states.pop(uid, None)
            self.last_active.pop(uid, None)
    
    # ===== Response Helpers =====
    def _create_response(self, content: str, next_step: str, **kwargs) -> Dict[str, Any]:
        """Create a standardized response dictionary."""
        response = {
            "type": kwargs.get('response_type', 'message'),  # Use provided response_type or default to 'message'
            "text": content,
            "content": content,
            "next_step": next_step,
            "is_user": False,
            "timestamp": datetime.now().isoformat(),
            "campaign_data": {}
        }
        # Only include buttons if they are provided
        if 'buttons' in kwargs:
            response['buttons'] = kwargs['buttons']
        return response
    
    def _parse_currency(self, amount_str: str) -> Optional[float]:
        """Parse currency string to float, handling various formats."""
        try:
            cleaned = re.sub(r'[^\d.]', '', amount_str)
            return float(cleaned) if cleaned else None
        except (ValueError, IndexError):
            return None
      
    # ===== Message Content =====
    def get_benefits(self) -> List[Dict[str, Any]]:
        """Return the benefits of Tabung Warisan."""
        return [
            {
                "title": "LIFETIME PROTECTION",
                "description": "Your legacy is protected for life.",
                "points": [
                    "Guaranteed payout to your beneficiaries",
                    "Coverage that lasts your entire lifetime",
                    "Financial security for your loved ones"
                ]
            },
            {
                "title": "WEALTH ACCUMULATION",
                "description": "Grow your wealth over time.",
                "points": [
                    "Cash value that grows tax-deferred",
                    "Potential for long-term growth",
                    "Flexible premium payment options"
                ]
            },
            {
                "title": "PEACE OF MIND",
                "description": "Know your family is taken care of.",
                "points": [
                    "Financial protection for your loved ones",
                    "No medical check-up required",
                    "Guaranteed acceptance"
                ]
            }
        ]
    
    def get_welcome_message(self) -> str:
        """Return the welcome message for the campaign."""
        return (
            "🌟 *Welcome to Tabung Warisan!* 🌟\n\n"
            "Protect your family's future with our legacy planning solution. "
            "With Tabung Warisan, you can ensure your loved ones are taken care of "
            "with guaranteed financial protection and wealth accumulation options."
        )
        
    def _get_welcome_response(self) -> Dict[str, Any]:
        """Helper method to get welcome message and buttons."""
        welcome_message = self.get_welcome_message()
        return {
            "type": "message",
            "text": welcome_message + "\n\nWould you like to learn more about the benefits?",
            "content": welcome_message + "\n\nWould you like to learn more about the benefits?",
            "buttons": [
                {"label": "✅ Yes, tell me more", "value": "yes_benefits"},
                {"label": "❌ Not now, thanks", "value": "no_thanks"}
            ],
            "next_step": "handle_welcome_response"
        }
        
    def _format_benefits(self, benefits: List[Dict[str, Any]]) -> str:
        """Format benefits list into a readable string."""
        formatted = []
        for benefit in benefits:
            formatted.append(f"*{benefit['title']}*")
            formatted.append(f"{benefit['description']}")
            for point in benefit['points']:
                formatted.append(f"• {point}")
            formatted.append("")
        return "\n".join(formatted)
        
    def _get_benefits_response(self) -> Dict[str, Any]:
        """Return the benefits information with action buttons."""
        benefits = self.get_benefits()
        benefits_text = self._format_benefits(benefits)
        question = "\n\nWould you like to see how much coverage you can get?"
        full_message = benefits_text + question
        
        return {
            "type": "buttons",  # Changed from "message" to "buttons" to trigger button display
            "text": full_message,
            "content": full_message,
            "buttons": [
                {"label": "✅ Yes, show me", "value": "yes_coverage"},
                {"label": "❌ Maybe later", "value": "no_thanks"},
            ],
            "next_step": "handle_benefits_response"
        }
    
    # ===== WebSocket Communication =====
    async def send_message(self, text: str, ws: Any = None) -> str:
        """Send text message through WebSocket if available."""
        try:
            if ws:
                await ws.send_text(json.dumps({"type": "message", "content": text}))
        except Exception as e:
            if ws and not getattr(ws, 'client_state', None) or not ws.client_state.disconnected:
                logger.error(f"Failed to send message: {str(e)}")
        return text
    
    async def send_buttons(self, text: str, buttons: List[Dict[str, str]], ws: Any = None) -> str:
        """Send interactive buttons through WebSocket if available."""
        try:
            if not ws:
                return text
                
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
                logger.warning("No valid buttons to send")
                return text
                
            # Send the message with buttons
            await ws.send_text(json.dumps({
                'type': 'buttons',
                'content': text,
                'buttons': valid_buttons
            }))
            return text
            
        except Exception as e:
            logger.error(f"Error sending buttons: {str(e)}")
            return await self.send_message(text, ws)
    
    # ===== Step Handlers =====
    async def _handle_legacy_amount(self, state: TabungWarisanState, message: str) -> Dict[str, Any]:
        """Process legacy amount input."""
        try:
            # Handle "Other Amount" selection
            if message.lower() in ["other", "other amount", "other_amount"]:
                return self._create_response(
                    "Please enter your desired legacy amount (minimum RM 1,000):",
                    "get_custom_legacy_amount"
                )
                
            # Extract numeric value from the message
            amount = float(''.join(c for c in message if c.isdigit() or c == '.'))
            
            # Validate minimum amount
            if amount < 1000:
                return {
                    "type": "buttons",
                    "text": "The minimum legacy amount is RM 1,000. Please select an amount:",
                    "content": "The minimum legacy amount is RM 1,000. Please select an amount:",
                    "buttons": [
                        {"label": "RM 500,000", "value": "500000"},
                        {"label": "RM 1,000,000", "value": "1000000"},
                        {"label": "RM 1,500,000", "value": "1500000"},
                        {"label": "RM 2,000,000", "value": "2000000"},
                        {"label": "Other Amount", "value": "other_amount"}
                    ],
                    "next_step": "get_legacy_amount"
                }
                
            # Store the amount
            state.desired_legacy = amount
            
            # Check if we already have age from user_data
            if hasattr(state, 'user_age') and state.user_age and 18 <= state.user_age <= 70:
                # Use the age from user_data
                age = state.user_age
                state.current_step = "calculate_premium"
                
                # Calculate premium
                premium = state.calculate_warisan_premium_estimation(amount, age)
                monthly_premium = premium / 12
                
                return {
                    "type": "buttons",
                    "content": (
                        f"Great! I see you are {age} years old and want to leave {format_currency(amount)} as a legacy.\n\n"
                        f"Your estimated premium would be:\n"
                        f"- Annual: *{format_currency(premium)}*\n"
                        f"- Monthly: *{format_currency(monthly_premium)}*\n\n"
                        "Would you like an agent to contact you to further discuss the plan?"
                    ),
                    "next_step": "offer_agent_contact",
                    "buttons": [
                        {"label": "✅ Yes, contact me", "value": "contact_agent"},
                        {"label": "❌ No thanks", "value": "no_contact"}
                    ]
                }
            else:
                # If no age in user_data, ask for age
                state.current_step = "get_age"
                return self._create_response(
                    f"Great! You want to leave {format_currency(amount)} as a legacy.\n\n"
                    "Now, may I know your current age? (18-70 years)",
                    "get_age"
                )
            
        except (ValueError, TypeError):
            return {
                "type": "buttons",
                "text": "Please select a valid legacy amount:",
                "content": "Please select a valid legacy amount:",
                "buttons": [
                    {"label": "RM 500,000", "value": "500000"},
                    {"label": "RM 1,000,000", "value": "1000000"},
                    {"label": "RM 1,500,000", "value": "1500000"},
                    {"label": "RM 2,000,000", "value": "2000000"},
                    {"label": "Other Amount", "value": "other_amount"}
                ],
                "next_step": "get_legacy_amount"
            }
    
    async def _handle_age(self, state: TabungWarisanState, message: str) -> Dict[str, Any]:
        """Process age input and calculate premium."""
        # First handle the case where we're coming from the age input
        if state.current_step == "get_age":
            try:
                age = int(message.strip())
                if not 18 <= age <= 70:
                    raise ValueError("Age out of range")
                
                state.user_age = age
                premium = state.calculate_warisan_premium_estimation(state.desired_legacy, age)
                
                # Calculate monthly premium (annual premium / 12)
                monthly_premium = premium / 12
                # Combine results with contact prompt
                result_message = (
                    f"Based on your age of {age} and desired legacy of {format_currency(state.desired_legacy)}, "
                    f"your estimated premium would be:\n"
                    f"- Annual: *{format_currency(premium)}*\n"
                    f"- Monthly: *{format_currency(monthly_premium)}*"
                )
                
                # Update the state
                state.current_step = "offer_agent_contact"
                
                return {
                    "type": "buttons",
                    "content": f"{result_message}\n\nWould you like an agent to contact you to further discuss the plan?",
                    "next_step": "offer_agent_contact",
                    "buttons": [
                        {"label": "✅ Yes, contact me", "value": "contact_agent"},
                        {"label": "❌ No thanks", "value": "no_contact"}
                    ]
                }
            except ValueError:
                return {
                    "type": "message",
                    "content": "Please enter a valid age between 18 and 70.",
                    "next_step": "get_age"
                }
        
        # Default return if not handling age input
        return {
            "type": "message",
            "content": "Please enter your age to continue.",
            "next_step": "get_age"
        }
    
    def _handle_agent_contact(self, state: TabungWarisanState, message) -> Dict[str, Any]:
        """Handle agent contact preference and navigation options."""
        try:
            logger.info(f"_handle_agent_contact received message: {message} (type: {type(message)})")
            if isinstance(message, dict):
                if 'value' in message:
                    message_value = message['value']
                elif 'text' in message:
                    message_value = message['text']
                else:
                    message_value = str(message)
                message_lower = str(message_value).lower().strip()
            else:
                message_lower = str(message).lower().strip()
            logger.info(f"Processed message_lower: {message_lower}")
            if message_lower == "contact_agent":
                logger.info("Contact agent selected. Prompting for contact info.")
                state.current_step = "get_contact_info"
                return {
                    "type": "message",
                    "content": "Please provide your contact information (phone or email) so our agent can reach you:",
                    "next_step": "get_contact_info"
                }
            elif message_lower == "no_contact":
                logger.info("No contact selected. Showing main menu and extra option button.")
                state.current_step = "main_menu"
                return {
                    "type": "buttons",
                    "content": "No problem! What would you like to do next?",
                    "buttons": [
                        {"label": "🏠 Return to Main Menu", "value": "main_menu"},
                        {"label": "❓ Ask another question", "value": "ask_question"}
                    ],
                    "next_step": "main_menu"
                }
            elif message_lower == "main_menu" or message_lower == "restart":
                logger.info("Main menu or restart selected. Signaling main.py to reset and start from get_name...")
                return {
                    "type": "reset_to_main",
                    "response": "Returning to main menu...",
                    "content": "Returning to main menu...",
                    "reset_to_main": True
                }
            else:
                return {
                    "type": "buttons",
                    "text": "Would you like an agent to contact you to further discuss the plan?",
                    "content": "Would you like an agent to contact you to further discuss the plan?",
                    "next_step": "offer_agent_contact",
                    "buttons": [
                        {"label": "✅ Yes, contact me", "value": "contact_agent"},
                        {"label": "❌ No thanks", "value": "no_contact"},
                        {"label": "🏠 Main Menu", "value": "main_menu"}
                    ]
                }
        except Exception as e:
            logger.error(f"Error in _handle_agent_contact: {str(e)}")
            return {
                "type": "message",
                "content": "I'm sorry, something went wrong. Let's try that again.",
                "next_step": "offer_agent_contact"
            }
    
    async def _handle_contact_info(self, state: TabungWarisanState, message: str) -> Dict[str, Any]:
        """Process and validate contact information."""
        try:
            contact = message.strip()
            is_email = re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", contact)
            is_phone = re.match(r"^(\+?6?01)[0-46-9]-*[0-9]{7,8}$", contact)
            if not (is_email or is_phone):
                return {
                    "type": "message",
                    "content": "Please enter a valid phone number or email address:",
                    "next_step": "get_contact_info"
                }
            state.user_data["contact_info"] = contact
            state.current_step = "contact_confirmed"
            return {
                "type": "buttons",
                "content": "Thank you for your interest! An agent will contact you soon.",
                "next_step": "contact_confirmed",
                "buttons": [
                    {"label": "🏠 Return to Main Menu", "value": "main_menu"},
                    {"label": "❓ Ask another question", "value": "ask_question"}
                ]
            }
        except Exception as e:
            logger.error(f"Error in _handle_contact_info: {str(e)}")
            return self._create_response(
                "Sorry, there was an error processing your request. Please try again.",
                "contact_confirmed"
            )
    
    # ===== Main Message Processor =====
    async def process_message(self, user_id: str, message: str, ws: Any = None, user_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process incoming message and return response.
        
        Args:
            user_id: Unique identifier for the user session
            message: User's input message
            ws: WebSocket connection for real-time updates
            user_data: Optional dictionary containing user data from main conversation
            
        Returns:
            Dict containing response and state information
        """
        try:
            state = self.get_state(user_id)
            logger.info(f"Processing message in TabungWarisan: {message}")
            
            # Update state with user data if provided (e.g., age from main conversation)
            if user_data:
                state.user_data.update(user_data)
                # Update age if available in user_data
                if 'age' in user_data and user_data['age']:
                    try:
                        state.user_age = int(user_data['age'])
                        logger.info(f"[TabungWarisan] Updated age from main conversation: {state.user_age}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[TabungWarisan] Invalid age in user_data: {user_data['age']}. Error: {e}")
                
                # Update name if available
                if 'name' in user_data and user_data['name']:
                    state.user_name = user_data.get('name')
                    logger.info(f"[TabungWarisan] Updated name from main conversation: {state.user_name}")
            
            # Handle main menu or restart request (reset state and show welcome)
            msg_lower = str(message).lower().strip() if not isinstance(message, dict) else str(message.get('value', message)).lower().strip()
            if msg_lower in ["main_menu", "restart", "start"]:
                # Signal main.py to reset to get_name step
                return {
                    "type": "reset_to_main",
                    "content": "Returning to main menu. Let's start again! What's your name?"
                }
            # Show welcome message on first interaction or when explicitly requested
            if state.current_step in ["", "welcome"] or not hasattr(state, 'welcome_shown'):
                state.current_step = "handle_welcome_response"
                state.welcome_shown = True
                return self._get_welcome_response()
                
            # If we're already handling welcome response, don't show welcome again
            if state.current_step == "handle_welcome_response" and message.lower() not in ["yes", "yes_benefits", "no", "no_thanks"]:
                return self._get_welcome_response()
                
            # Handle welcome response
            if state.current_step == "handle_welcome_response":
                msg_lower = message.lower()
                if msg_lower in ["yes", "yes_benefits"]:
                    state.current_step = "handle_benefits_response"
                    return self._get_benefits_response()
                elif msg_lower in ["no", "no_thanks", "maybe later", "later", "tidak", "tak", "x", "nope"]:
                    # Show only the Return to Main Menu button after any negative response
                    return {
                        "type": "buttons",
                        "content": "No problem! If you wish to return to the main menu and restart the bot, click below.",
                        "buttons": [
                            {"label": "🔄 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                else:
                    return self._get_welcome_response()
                    
            # Handle benefits response
            if state.current_step == "handle_benefits_response":
                msg_lower = message.lower()
                if msg_lower in ["yes", "yes_coverage"]:
                    state.current_step = "get_legacy_amount"
                    return {
                        "type": "buttons",
                        "text": "Great! To calculate your coverage, I'll need a few details.\n\n"
                               "How much would you like to leave as a legacy for your loved ones?",
                        "content": "Great! To calculate your coverage, I'll need a few details.\n\n"
                                   "How much would you like to leave as a legacy for your loved ones?",
                        "buttons": [
                            {"label": "RM 500,000", "value": "500000"},
                            {"label": "RM 1,000,000", "value": "1000000"},
                            {"label": "RM 1,500,000", "value": "1500000"},
                            {"label": "RM 2,000,000", "value": "2000000"},
                            {"label": "Other Amount", "value": "other_amount"}
                        ],
                        "next_step": "get_legacy_amount"
                    }
                elif msg_lower in ["no", "no_thanks", "maybe later", "later", "tidak", "tak", "x", "nope"]:
                    # Show only the Return to Main Menu button after any negative response
                    return {
                        "type": "buttons",
                        "content": "No problem! If you wish to return to the main menu and restart the bot, click below.",
                        "buttons": [
                            {"label": "🔄 Return to Main Menu", "value": "main_menu"}
                        ]
                    }
                else:
                    return self._get_benefits_response()
                    
            # Handle legacy amount selection
            if state.current_step == "get_legacy_amount":
                if message.lower() in ["other", "other amount", "other_amount"]:
                    state.current_step = "get_custom_legacy_amount"
                    return self._create_response(
                        "Please enter your desired legacy amount (minimum RM 1,000):",
                        "get_custom_legacy_amount"
                    )
                try:
                    # Extract numeric value from the message
                    amount = float(''.join(c for c in message if c.isdigit() or c == '.'))
                    state.desired_legacy = amount
                    state.current_step = "get_age"
                    
                    # Check if we already have age from user_data
                    if hasattr(state, 'user_age') and state.user_age and 18 <= state.user_age <= 70:
                        # Use the age from user_data
                        age = state.user_age
                        state.current_step = "calculate_premium"
                        
                        # Calculate premium
                        premium = state.calculate_warisan_premium_estimation(amount, age)
                        monthly_premium = premium / 12


                        try:
                            name = state.user_data.get("name","N/A")
                            dob = state.user_data.get("dob","")
                            email = state.user_data.get("email", "")
                            primary_concern = state.user_data.get("primary_concern", "")
                            life_stage = state.user_data.get("life_stage", "")
                            dependents = state.user_data.get("dependents", "")
                            existing_coverage = state.user_data.get("existing_coverage", "")
                            premium_budget = state.user_data.get("premium_budget", "")
                            selected_plan = "tabung_warisan"  

                            legacy_amount_str = str(amount)
                            
                            row_data = [
                        name, dob, email, primary_concern, life_stage, dependents,
                        existing_coverage, premium_budget, selected_plan,
                        None, None,  # SKIP 2 LAJUR: Kosongkan untuk annual_income & coverage (sgsa.py)
                        legacy_amount_str  # Data legacy: Jumlah warisan & umur
                          ]
                            append_row_to_sheet(row_data)
                            logger.info(f"[TABUNG_WARISAN] Data legacy dimasukkan ke Google Sheet: Legacy Amount={legacy_amount_str} untuk user {user_id if 'user_id' in locals() else 'unknown'}")

                        except Exception as sheet_error:
                            logger.error (f"[tabung_warisan] Error inserting legacy data to Google Sheet: {str(sheet_error)}")

                        return {
                            "type": "buttons",
                            "content": (
                                f"Great! I see you are {age} years old and want to leave {format_currency(amount)} as a legacy.\n\n"
                                f"Your estimated premium would be:\n"
                                f"- Annual: *{format_currency(premium)}*\n"
                                f"- Monthly: *{format_currency(monthly_premium)}*\n\n"
                                "Would you like an agent to contact you to further discuss the plan?"
                            ),
                            "next_step": "offer_agent_contact",
                            "buttons": [
                                {"label": "✅ Yes, contact me", "value": "contact_agent"},
                                {"label": "❌ No thanks", "value": "no_contact"}
                            ]
                        }
                    
                    # If no age in user_data, ask for age
                    return self._create_response(
                        f"Great! You want to leave {format_currency(amount)} as a legacy.\n\n"
                        "Now, may I know your current age? (18-70 years)",
                        "get_age"
                    )
                except (ValueError, TypeError):
                    return {
                        "type": "buttons",
                        "content": "Please select a valid legacy amount:",
                        "next_step": "get_legacy_amount",
                        "buttons": [
                            {"label": "RM 500,000", "value": "500000"},
                            {"label": "RM 1,000,000", "value": "1000000"},
                            {"label": "RM 1,500,000", "value": "1500000"},
                            {"label": "RM 2,000,000", "value": "2000000"},
                            {"label": "Other Amount", "value": "other_amount"}
                        ]
                    }

            # Handle custom legacy amount input
            if state.current_step == "get_custom_legacy_amount":
                try:
                    # Extract numeric value from the message
                    amount = float(''.join(c for c in message if c.isdigit() or c == '.'))
                    
                    # Validate minimum amount
                    if amount < 1000:
                        return self._create_response(
                            "The minimum legacy amount is RM 1,000. Please enter a higher amount:",
                            "get_custom_legacy_amount"
                        )
                        
                    # Store the amount and move to age input
                    state.desired_legacy = amount
                    state.current_step = "get_age"
                    
                    # Check if we already have age from user_data
                    if hasattr(state, 'user_age') and state.user_age and 18 <= state.user_age <= 70:
                        # Use the age from user_data
                        age = state.user_age
                        state.current_step = "calculate_premium"
                        
                        # Calculate premium
                        premium = state.calculate_warisan_premium_estimation(amount, age)
                        monthly_premium = premium / 12
                        
                        return {
                            "type": "buttons",
                            "content": (
                                f"Great! I see you are {age} years old and want to leave {format_currency(amount)} as a legacy.\n\n"
                                f"Your estimated premium would be:\n"
                                f"- Annual: *{format_currency(premium)}*\n"
                                f"- Monthly: *{format_currency(monthly_premium)}*\n\n"
                                "Would you like an agent to contact you to further discuss the plan?"
                            ),
                            "next_step": "offer_agent_contact",
                            "buttons": [
                                {"label": "✅ Yes, contact me", "value": "contact_agent"},
                                {"label": "❌ No thanks", "value": "no_contact"}
                            ]
                        }
                    
                    return self._create_response(
                        f"Great! You want to leave {format_currency(amount)} as a legacy.\n\n"
                        "Now, may I know your current age? (18-70 years)",
                        "get_age"
                    )
                    
                except (ValueError, TypeError):
                    return self._create_response(
                        "Please enter a valid amount (e.g., 100000 or 100,000):",
                        "get_custom_legacy_amount"
                    )
                    
            # Handle age input
            if state.current_step == "get_age":
                return await self._handle_age(state, message)
                
            # Handle agent contact offer
            if state.current_step == "offer_agent_contact":
                logger.info(f"Processing offer_agent_contact with message: {message} (type: {type(message)})")
                result = self._handle_agent_contact(state, message)
                logger.info(f"_handle_agent_contact returned: {result}")
                return result

            # Handle contact info collection
            if state.current_step == "get_contact_info":
                return await self._handle_contact_info(state, message)

            # Handle end of conversation and post-contact navigation
            if state.current_step in ["end_conversation", "contact_confirmed"]:
                return {
                    "type": "buttons",
                    "content": "Thank you for your interest! An agent will contact you soon. You may return to the main menu below.",
                    "next_step": "main_menu",
                    "buttons": [
                        {"label": "🏠 Return to Main Menu", "value": "main_menu"}
                    ]
                }

            # Fallback for unhandled steps: always reset and show main menu
            logger.warning(f"Unhandled step: {state.current_step}. Resetting to main menu.")
            state.reset()
            return {
                "type": "reset_to_main",
                "response": "Returning to main menu...",
                "content": "Returning to main menu...",
                "reset_to_main": True
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Error in process_message: {str(e)}\n{error_details}")
            return {
                "type": "message",
                "content": "I'm sorry, something went wrong. The error has been logged. Let's start over.",
                "next_step": "welcome"
            }

# Create the campaign instance with the exact name expected by main.py
tabung_warisan_campaign_instance = TabungWarisanCampaign()

# Alias for backward compatibility
tabung_warisan_campaign = tabung_warisan_campaign_instance
